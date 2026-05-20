"""
Hermes Web UI -- File upload: multipart parser and upload handler.
"""
import mimetypes
import os
import re as _re
import email.parser
import tempfile
import shutil
from pathlib import Path, PurePosixPath

from api.config import MAX_UPLOAD_BYTES, STATE_DIR
from api.helpers import j, bad, safe_resolve
from api.models import get_session
from api.workspace import safe_resolve_ws

_MAX_EXTRACTED_BYTES = 10 * MAX_UPLOAD_BYTES
_WORKSPACE_UPLOAD_CHUNK_MAX_BYTES = 512 * 1024


def parse_multipart(rfile, content_type, content_length) -> tuple:
    import re as _re, email.parser as _ep
    m = _re.search(r'boundary=([^;\s]+)', content_type)
    if not m:
        raise ValueError('No boundary in Content-Type')
    boundary = m.group(1).strip('"').encode()
    raw = rfile.read(content_length)
    fields = {}
    files = {}
    delimiter = b'--' + boundary
    end_marker = b'--' + boundary + b'--'
    parts = raw.split(delimiter)
    for part in parts[1:]:
        stripped = part.lstrip(b'\r\n')
        if stripped.startswith(b'--'):
            break
        sep = b'\r\n\r\n' if b'\r\n\r\n' in part else b'\n\n'
        if sep not in part:
            continue
        header_raw, body = part.split(sep, 1)
        if body.endswith(b'\r\n'):
            body = body[:-2]
        elif body.endswith(b'\n'):
            body = body[:-1]
        header_text = header_raw.lstrip(b'\r\n').decode('utf-8', errors='replace')
        msg = _ep.HeaderParser().parsestr(header_text)
        disp = msg.get('Content-Disposition', '')
        name_m = _re.search(r'name="([^"]*)"', disp)
        file_m = _re.search(r'filename="([^"]*)"', disp)
        if not name_m:
            continue
        name = name_m.group(1)
        if file_m:
            files[name] = (file_m.group(1), body)
        else:
            fields[name] = body.decode('utf-8', errors='replace')
    return fields, files


def _sanitize_upload_name(filename: str) -> str:
    safe_name = _re.sub(r'[^\w.\-]', '_', Path(filename).name)[:200]
    if not safe_name or safe_name.strip('.') == '':
        raise ValueError('Invalid filename')
    return safe_name


def _normalize_workspace_upload_relpath(rel_path: str, fallback_filename: str = '') -> str:
    """Return a browser-supplied relative upload path safe for workspace writes.

    Workspace drag/drop uploads need to preserve local folder structure, so this
    deliberately keeps spaces and unicode in path components instead of applying
    the attachment-inbox filename sanitizer.  Traversal, absolute paths, drive
    roots, empty names, and NUL bytes are rejected before the path is passed to
    the workspace-boundary resolver for the final containment check.
    """
    raw = str(rel_path or fallback_filename or '').replace('\\', '/').strip()
    if not raw:
        raise ValueError('Invalid upload path')
    if raw.startswith('/') or _re.match(r'^[A-Za-z]:', raw):
        raise ValueError('Invalid upload path')
    parts = []
    for part in raw.split('/'):
        part = part.strip()
        if not part or part == '.':
            continue
        if part == '..' or '\x00' in part:
            raise ValueError('Invalid upload path')
        parts.append(part)
    if not parts:
        raise ValueError('Invalid upload path')
    return '/'.join(parts)


def _normalize_workspace_upload_dir(dir_path: str) -> str:
    raw = str(dir_path or '.').replace('\\', '/').strip()
    if raw in ('', '.'):
        return '.'
    return _normalize_workspace_upload_relpath(raw)


def _workspace_upload_result_path(dir_path: str, rel_path: str) -> str:
    dir_path = _normalize_workspace_upload_dir(dir_path)
    rel_path = _normalize_workspace_upload_relpath(rel_path)
    return rel_path if dir_path == '.' else f'{dir_path.rstrip("/")}/{rel_path}'


def _parse_int_field(fields: dict, name: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(str(fields.get(name, '')).strip())
    except (TypeError, ValueError):
        raise ValueError(f'Invalid {name}')
    if minimum is not None and value < minimum:
        raise ValueError(f'Invalid {name}')
    if maximum is not None and value > maximum:
        raise ValueError(f'Invalid {name}')
    return value


def _workspace_chunk_upload_id(raw: str) -> str:
    upload_id = _re.sub(r'[^A-Za-z0-9_.-]', '_', str(raw or '').strip())[:120]
    if not upload_id or upload_id.strip('._-') == '':
        raise ValueError('Invalid upload id')
    return upload_id


def _workspace_chunk_temp_path(dest: Path, upload_id: str) -> Path:
    safe_name = _re.sub(r'[^\w.\-]', '_', dest.name)[:120] or 'upload'
    dest_parent = dest.parent.resolve()
    temp = (dest_parent / f'.{safe_name}.{upload_id}.part').resolve()
    if not temp.is_relative_to(dest_parent):
        raise ValueError('Invalid upload destination')
    return temp


def _attachment_root() -> Path:
    """Return the configured upload inbox root.

    Plain chat attachments are transient context for the agent, not project
    source files.  Keep them out of the active workspace by default while still
    allowing operators to move the inbox with HERMES_WEBUI_ATTACHMENT_DIR.
    """
    override = os.getenv('HERMES_WEBUI_ATTACHMENT_DIR', '').strip()
    if override:
        return Path(override).expanduser().resolve()
    return (STATE_DIR / 'attachments').resolve()


def _upload_destination(session_id: str, safe_name: str) -> Path:
    dest_dir = _session_attachment_dir(session_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = (dest_dir / safe_name).resolve()
    if not dest.is_relative_to(dest_dir):
        raise ValueError('Invalid upload destination')
    return dest


def _session_attachment_dir(session_id: str, *, root: Path | None = None) -> Path:
    root = (root or _attachment_root()).resolve()
    dest_dir = (root / _re.sub(r'[^\w.\-]', '_', str(session_id or 'session'))[:120]).resolve()
    if not dest_dir.is_relative_to(root):
        raise ValueError('Invalid attachment directory')
    return dest_dir


def handle_upload(handler):
    import traceback as _tb
    try:
        content_type = handler.headers.get('Content-Type', '')
        content_length = int(handler.headers.get('Content-Length', 0) or 0)
        if content_length > MAX_UPLOAD_BYTES:
            return j(handler, {'error': f'File too large (max {MAX_UPLOAD_BYTES//1024//1024}MB)'}, status=413)
        fields, files = parse_multipart(handler.rfile, content_type, content_length)
        session_id = fields.get('session_id', '')
        if 'file' not in files:
            return j(handler, {'error': 'No file field in request'}, status=400)
        filename, file_bytes = files['file']
        if not filename:
            return j(handler, {'error': 'No filename in upload'}, status=400)
        try:
            s = get_session(session_id)
        except KeyError:
            return j(handler, {'error': 'Session not found'}, status=404)
        safe_name = _sanitize_upload_name(filename)
        dest = _upload_destination(session_id, safe_name)
        dest.write_bytes(file_bytes)
        mime = mimetypes.guess_type(safe_name)[0] or 'application/octet-stream'
        return j(handler, {
            'filename': safe_name,
            'path': str(dest),
            'size': dest.stat().st_size,
            'mime': mime,
            'is_image': mime.startswith('image/'),
        })
    except ValueError as e:
        return j(handler, {'error': str(e)}, status=400)
    except Exception:
        print('[webui] upload error: ' + _tb.format_exc(), flush=True)
        return j(handler, {'error': 'Upload failed'}, status=500)


def handle_workspace_upload(handler):
    """Upload one multipart file directly into the active session workspace.

    This is separate from ``/api/upload`` because composer attachments live in a
    per-session inbox outside the project tree. Workspace-panel drops are an
    explicit file-system mutation, so the client supplies both the target
    workspace directory (``dir``) and the browser-relative file path
    (``rel_path``) used to preserve dropped folder subtrees.
    """
    import traceback as _tb
    try:
        content_type = handler.headers.get('Content-Type', '')
        content_length = int(handler.headers.get('Content-Length', 0) or 0)
        if content_length > MAX_UPLOAD_BYTES:
            return j(handler, {'error': f'File too large (max {MAX_UPLOAD_BYTES//1024//1024}MB)'}, status=413)
        fields, files = parse_multipart(handler.rfile, content_type, content_length)
        session_id = fields.get('session_id', '')
        if 'file' not in files:
            return j(handler, {'error': 'No file field in request'}, status=400)
        filename, file_bytes = files['file']
        if not filename:
            return j(handler, {'error': 'No filename in upload'}, status=400)
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            return j(handler, {'error': f'File too large (max {MAX_UPLOAD_BYTES//1024//1024}MB)'}, status=413)
        try:
            s = get_session(session_id)
        except KeyError:
            return j(handler, {'error': 'Session not found'}, status=404)

        target_dir = _normalize_workspace_upload_dir(fields.get('dir', '.'))
        rel_path = _normalize_workspace_upload_relpath(fields.get('rel_path', ''), filename)
        workspace = Path(s.workspace)
        base_dir = safe_resolve(workspace, target_dir)
        if not base_dir.exists():
            return j(handler, {'error': 'Target directory not found'}, status=404)
        if not base_dir.is_dir():
            return j(handler, {'error': 'Target path is not a directory'}, status=400)

        result_path = _workspace_upload_result_path(target_dir, rel_path)
        dest = safe_resolve(workspace, result_path)
        if dest.exists() and dest.is_dir():
            return j(handler, {'error': 'Upload destination is a directory'}, status=400)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(file_bytes)
        safe_filename = PurePosixPath(rel_path).name
        mime = mimetypes.guess_type(safe_filename)[0] or 'application/octet-stream'
        return j(handler, {
            'ok': True,
            'filename': safe_filename,
            'path': result_path,
            'size': dest.stat().st_size,
            'mime': mime,
            'is_image': mime.startswith('image/'),
        })
    except ValueError as e:
        return j(handler, {'error': str(e)}, status=400)
    except PermissionError as e:
        return j(handler, {'error': str(e) or 'Permission denied'}, status=403)
    except Exception:
        print('[webui] workspace upload error: ' + _tb.format_exc(), flush=True)
        return j(handler, {'error': 'Workspace upload failed'}, status=500)


def handle_workspace_upload_chunk(handler):
    """Receive one chunk of a workspace-panel upload and assemble it on disk.

    Large workspace files may cross a reverse proxy that rejects large request
    bodies before WebUI can enforce ``MAX_UPLOAD_BYTES`` itself.  The browser
    sends those files as small, sequential chunks to this endpoint; each request
    stays proxy-friendly while the assembled file remains subject to the normal
    workspace path and total-size guards.
    """
    import traceback as _tb
    try:
        content_type = handler.headers.get('Content-Type', '')
        content_length = int(handler.headers.get('Content-Length', 0) or 0)
        if content_length > _WORKSPACE_UPLOAD_CHUNK_MAX_BYTES + 128 * 1024:
            return j(handler, {'error': 'Upload chunk too large'}, status=413)
        fields, files = parse_multipart(handler.rfile, content_type, content_length)
        if 'file' not in files:
            return j(handler, {'error': 'No file field in request'}, status=400)

        filename, file_bytes = files['file']
        if len(file_bytes) > _WORKSPACE_UPLOAD_CHUNK_MAX_BYTES:
            return j(handler, {'error': 'Upload chunk too large'}, status=413)
        if not filename:
            return j(handler, {'error': 'No filename in upload'}, status=400)

        total_size = _parse_int_field(fields, 'total_size', minimum=0)
        if total_size > MAX_UPLOAD_BYTES:
            return j(handler, {'error': f'File too large (max {MAX_UPLOAD_BYTES//1024//1024}MB)'}, status=413)
        chunk_index = _parse_int_field(fields, 'chunk_index', minimum=0)
        chunk_count = _parse_int_field(fields, 'chunk_count', minimum=1)
        chunk_start = _parse_int_field(fields, 'chunk_start', minimum=0, maximum=total_size)
        if chunk_index >= chunk_count:
            raise ValueError('Invalid chunk_index')
        if chunk_start + len(file_bytes) > total_size:
            raise ValueError('Upload chunk exceeds declared file size')
        if chunk_index == 0 and chunk_start != 0:
            raise ValueError('Invalid first chunk offset')

        upload_id = _workspace_chunk_upload_id(fields.get('upload_id', ''))
        session_id = fields.get('session_id', '')
        try:
            s = get_session(session_id)
        except KeyError:
            return j(handler, {'error': 'Session not found'}, status=404)

        target_dir = _normalize_workspace_upload_dir(fields.get('dir', '.'))
        rel_path = _normalize_workspace_upload_relpath(fields.get('rel_path', ''), filename)
        workspace = Path(s.workspace)
        base_dir = safe_resolve(workspace, target_dir)
        if not base_dir.exists():
            return j(handler, {'error': 'Target directory not found'}, status=404)
        if not base_dir.is_dir():
            return j(handler, {'error': 'Target path is not a directory'}, status=400)

        result_path = _workspace_upload_result_path(target_dir, rel_path)
        dest = safe_resolve(workspace, result_path)
        if dest.exists() and dest.is_dir():
            return j(handler, {'error': 'Upload destination is a directory'}, status=400)
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp = _workspace_chunk_temp_path(dest, upload_id)

        if chunk_index == 0:
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                pass
        elif not temp.exists():
            return j(handler, {'error': 'Upload chunk sequence is incomplete'}, status=409)

        current_size = temp.stat().st_size if temp.exists() else 0
        if current_size != chunk_start:
            return j(handler, {'error': 'Upload chunk offset mismatch'}, status=409)

        with temp.open('ab') as fh:
            fh.write(file_bytes)
        written = temp.stat().st_size
        if written > total_size:
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                pass
            raise ValueError('Upload exceeded declared file size')

        complete = chunk_index == chunk_count - 1
        if not complete:
            return j(handler, {
                'ok': True,
                'complete': False,
                'chunk_index': chunk_index,
                'received': written,
                'size': total_size,
            })

        if written != total_size:
            return j(handler, {'error': 'Upload ended before declared file size'}, status=400)

        try:
            temp.replace(dest)
        except OSError:
            shutil.move(str(temp), str(dest))

        safe_filename = PurePosixPath(rel_path).name
        mime = mimetypes.guess_type(safe_filename)[0] or 'application/octet-stream'
        return j(handler, {
            'ok': True,
            'complete': True,
            'filename': safe_filename,
            'path': result_path,
            'size': dest.stat().st_size,
            'mime': mime,
            'is_image': mime.startswith('image/'),
        })
    except ValueError as e:
        return j(handler, {'error': str(e)}, status=400)
    except PermissionError as e:
        return j(handler, {'error': str(e) or 'Permission denied'}, status=403)
    except Exception:
        print('[webui] workspace chunk upload error: ' + _tb.format_exc(), flush=True)
        return j(handler, {'error': 'Workspace upload failed'}, status=500)


def extract_archive(file_bytes: bytes, filename: str, workspace: Path):
    """Extract a zip or tar archive into the workspace.

    Returns a dict with ``extracted`` (int), ``files`` (list[str]).
    Raises ValueError on zip-slip or unsupported format.
    """
    import zipfile, tarfile, io, os, shutil

    name = Path(filename).name
    stem = Path(filename).stem  # strip .zip / .tar.gz etc.

    if name.lower().endswith(('.zip',)):
        _mode = 'zip'
    elif name.lower().endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz')):
        _mode = 'tar'
    else:
        raise ValueError(f'Unsupported archive format: {filename}')

    # Determine destination directory — use archive stem as folder name
    dest_dir = safe_resolve_ws(workspace, stem)
    # Avoid overwriting existing files by appending a suffix
    if dest_dir.exists():
        import string, random
        while dest_dir.exists():
            suffix = ''.join(random.choices(string.digits, k=3))
            dest_dir = dest_dir.with_name(stem + '_' + suffix)
    dest_dir.mkdir(parents=True, exist_ok=True)

    extracted_files = []
    total_extracted = 0

    try:
        if _mode == 'zip':
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                for member in zf.infolist():
                    # Skip directories
                    if member.is_dir():
                        continue
                    # Zip-slip protection
                    member_path = (dest_dir / member.filename).resolve()
                    if not member_path.is_relative_to(dest_dir.resolve()):
                        raise ValueError(f'Zip-slip blocked: {member.filename}')
                    # Zip-bomb protection: track actual extracted bytes (not declared file_size)
                    if total_extracted > _MAX_EXTRACTED_BYTES:
                        raise ValueError(
                            f'Extraction too large ({total_extracted // (1024*1024)} MB > '
                            f'{_MAX_EXTRACTED_BYTES // (1024*1024)} MB limit). '
                            f'Possible zip bomb.'
                        )
                    member_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(member_path, 'wb') as dst:
                        _chunk_size = 65536
                        while True:
                            chunk = src.read(_chunk_size)
                            if not chunk:
                                break
                            total_extracted += len(chunk)
                            if total_extracted > _MAX_EXTRACTED_BYTES:
                                raise ValueError(
                                    f'Extraction too large (> '
                                    f'{_MAX_EXTRACTED_BYTES // (1024*1024)} MB limit). '
                                    f'Possible zip bomb.'
                                )
                            dst.write(chunk)
                    extracted_files.append(str(member_path.relative_to(workspace.resolve())))

        elif _mode == 'tar':
            with tarfile.open(fileobj=io.BytesIO(file_bytes)) as tf:
                for member in tf.getmembers():
                    if not member.isfile():
                        continue
                    # Tar-slip protection
                    member_path = (dest_dir / member.name).resolve()
                    if not member_path.is_relative_to(dest_dir.resolve()):
                        raise ValueError(f'Tar-slip blocked: {member.name}')
                    # Tar-bomb protection: track actual extracted bytes (not declared size)
                    if total_extracted > _MAX_EXTRACTED_BYTES:
                        raise ValueError(
                            f'Extraction too large ({total_extracted // (1024*1024)} MB > '
                            f'{_MAX_EXTRACTED_BYTES // (1024*1024)} MB limit). '
                            f'Possible zip bomb.'
                        )
                    member_path.parent.mkdir(parents=True, exist_ok=True)
                    src_obj = tf.extractfile(member)
                    if src_obj:
                        with src_obj as src, open(member_path, 'wb') as dst:
                            _chunk_size = 65536
                            while True:
                                chunk = src.read(_chunk_size)
                                if not chunk:
                                    break
                                total_extracted += len(chunk)
                                if total_extracted > _MAX_EXTRACTED_BYTES:
                                    raise ValueError(
                                        f'Extraction too large (> '
                                        f'{_MAX_EXTRACTED_BYTES // (1024*1024)} MB limit). '
                                        f'Possible zip bomb.'
                                    )
                                dst.write(chunk)
                    extracted_files.append(str(member_path.relative_to(workspace.resolve())))
    except Exception:
        # Clean up partially-extracted directory to avoid orphaned folders
        try:
            shutil.rmtree(dest_dir, ignore_errors=True)
        except Exception:
            pass
        raise

    return {'extracted': len(extracted_files), 'files': extracted_files, 'dest': str(dest_dir)}


def handle_upload_extract(handler):
    """Handle archive upload and extraction."""
    import traceback as _tb
    try:
        content_type = handler.headers.get('Content-Type', '')
        content_length = int(handler.headers.get('Content-Length', 0) or 0)
        if content_length > MAX_UPLOAD_BYTES:
            return j(handler, {'error': f'File too large (max {MAX_UPLOAD_BYTES//1024//1024}MB)'}, status=413)
        fields, files = parse_multipart(handler.rfile, content_type, content_length)
        session_id = fields.get('session_id', '')
        if 'file' not in files:
            return j(handler, {'error': 'No file field in request'}, status=400)
        filename, file_bytes = files['file']
        if not filename:
            return j(handler, {'error': 'No filename in upload'}, status=400)
        try:
            s = get_session(session_id)
        except KeyError:
            return j(handler, {'error': 'Session not found'}, status=404)
        workspace = Path(s.workspace)
        result = extract_archive(file_bytes, filename, workspace)
        return j(handler, {'ok': True, **result})
    except ValueError as e:
        return j(handler, {'error': str(e)}, status=400)
    except Exception:
        print('[webui] upload extract error: ' + _tb.format_exc(), flush=True)
        return j(handler, {'error': 'Archive extraction failed'}, status=500)


def handle_transcribe(handler):
    import traceback as _tb
    temp_path = None
    try:
        content_type = handler.headers.get('Content-Type', '')
        content_length = int(handler.headers.get('Content-Length', 0) or 0)
        if content_length > MAX_UPLOAD_BYTES:
            return j(handler, {'error': f'File too large (max {MAX_UPLOAD_BYTES//1024//1024}MB)'}, status=413)
        fields, files = parse_multipart(handler.rfile, content_type, content_length)
        if 'file' not in files:
            return j(handler, {'error': 'No file field in request'}, status=400)
        filename, file_bytes = files['file']
        if not filename:
            return j(handler, {'error': 'No filename in upload'}, status=400)
        safe_name = _sanitize_upload_name(filename)
        suffix = Path(safe_name).suffix or '.webm'
        with tempfile.NamedTemporaryFile(prefix='webui-stt-', suffix=suffix, delete=False) as tmp:
            temp_path = tmp.name
            tmp.write(file_bytes)
        try:
            from tools.transcription_tools import transcribe_audio
        except ImportError:
            return j(handler, {'error': 'Speech-to-text is unavailable on this server'}, status=503)
        result = transcribe_audio(temp_path)
        if not result.get('success'):
            msg = str(result.get('error') or 'Transcription failed')
            status = 503 if 'unavailable' in msg.lower() or 'not configured' in msg.lower() else 400
            return j(handler, {'error': msg}, status=status)
        transcript = str(result.get('transcript') or '').strip()
        return j(handler, {'ok': True, 'transcript': transcript})
    except ValueError as e:
        return j(handler, {'error': str(e)}, status=400)
    except Exception:
        print('[webui] transcribe error: ' + _tb.format_exc(), flush=True)
        return j(handler, {'error': 'Transcription failed'}, status=500)
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass

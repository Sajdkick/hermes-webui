import subprocess
import textwrap


def test_ops_projects_mount_renders_projects_button():
    script = textwrap.dedent(
        """
        const fs = require('fs');
        const vm = require('vm');

        class Root {
          constructor(){
            this.innerHTML = '';
            this.listeners = {};
          }
          addEventListener(name, handler){
            this.listeners[name] = handler;
          }
          querySelector(){
            return null;
          }
        }

        const source = fs.readFileSync('static/ops-projects.js', 'utf8');
        const context = {
          console,
          window: {},
          fetch: async () => ({ ok: true, json: async () => ({ projects: [] }) }),
          HTMLFormElement: function HTMLFormElement(){},
          HTMLElement: function HTMLElement(){},
          HTMLInputElement: function HTMLInputElement(){},
        };
        vm.createContext(context);
        vm.runInContext(source, context);
        if (!context.window.HermesOpsProjects || typeof context.window.HermesOpsProjects.mount !== 'function'){
          throw new Error('mount helper was not exported');
        }
        const root = new Root();
        context.window.HermesOpsProjects.mount(root, {
          phase: 'phase-2',
          route: '/ops',
          apiBase: '/api/ops',
          version: 'test-version',
        });
        if (!root.innerHTML.includes('Projects')){
          throw new Error('Projects button was not rendered');
        }
        if (!root.innerHTML.includes('phase-2')){
          throw new Error('Phase metadata was not rendered');
        }
        console.log('ok');
        """
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "ok"

(function(){
  window.HermesOpsModules=window.HermesOpsModules||{};

  function bindDashboard(ctx){
    const OPS=ctx&&ctx.OPS;
    const root=ctx&&ctx.root;
    const showError=ctx&&ctx.showError;
    const setBusy=ctx&&ctx.setBusy;
    const handleHomeAction=ctx&&ctx.handleHomeAction;
    const loadMigrationHealth=ctx&&ctx.loadMigrationHealth;
    const loadArtifactHealth=ctx&&ctx.loadArtifactHealth;
    const scanStaleRuns=ctx&&ctx.scanStaleRuns;
    const loadNotificationDiagnostics=ctx&&ctx.loadNotificationDiagnostics;
    const toggleNotificationSetting=ctx&&ctx.toggleNotificationSetting;
    const clearNotificationLogs=ctx&&ctx.clearNotificationLogs;
    const deletePushSubscription=ctx&&ctx.deletePushSubscription;
    const subscribeBrowserPush=ctx&&ctx.subscribeBrowserPush;
    const unsubscribeBrowserPush=ctx&&ctx.unsubscribeBrowserPush;
    const sendTestPushNotification=ctx&&ctx.sendTestPushNotification;
    const toggleAutoApprovalPolicy=ctx&&ctx.toggleAutoApprovalPolicy;
    const deleteAutoApprovalRule=ctx&&ctx.deleteAutoApprovalRule;
    const loadDatabaseSettings=ctx&&ctx.loadDatabaseSettings;
    const inspectDatabaseTables=ctx&&ctx.inspectDatabaseTables;
    const loadProjects=ctx&&ctx.loadProjects;
    const renderProjects=ctx&&ctx.renderProjects;
    const loadGitHubStatus=ctx&&ctx.loadGitHubStatus;
    const searchGitHubRepositories=ctx&&ctx.searchGitHubRepositories;
    const loadGitHubBranches=ctx&&ctx.loadGitHubBranches;
    const importGitHubRepository=ctx&&ctx.importGitHubRepository;
    const openProjects=ctx&&ctx.openProjects;
    const openOpsDashboard=ctx&&ctx.openOpsDashboard;
    const openProjectDetail=ctx&&ctx.openProjectDetail;
    const refreshDetail=ctx&&ctx.refreshDetail;
    const deleteProject=ctx&&ctx.deleteProject;
    const setTaskFilterStatus=ctx&&ctx.setTaskFilterStatus;
    const renderProjectDetail=ctx&&ctx.renderProjectDetail;
    const executeReadyTasksWithAi=ctx&&ctx.executeReadyTasksWithAi;
    const setEpicCollapsed=ctx&&ctx.setEpicCollapsed;
    const isEpicCollapsed=ctx&&ctx.isEpicCollapsed;
    const executeTask=ctx&&ctx.executeTask;
    const showToast=ctx&&ctx.showToast;
    const markTaskNeedsMoreWork=ctx&&ctx.markTaskNeedsMoreWork;
    const resetTaskFilters=ctx&&ctx.resetTaskFilters;
    const findTask=ctx&&ctx.findTask;
    const uploadTaskImage=ctx&&ctx.uploadTaskImage;
    const newChatInProject=ctx&&ctx.newChatInProject;
    const findProject=ctx&&ctx.findProject;
    const openOpsSession=ctx&&ctx.openOpsSession;
    const openRunTarget=ctx&&ctx.openRunTarget;
    const openRunDetail=ctx&&ctx.openRunDetail;
    const closeRunDetail=ctx&&ctx.closeRunDetail;
    const setRunStatus=ctx&&ctx.setRunStatus;
    const completeRun=ctx&&ctx.completeRun;
    const setOpsSessionClosed=ctx&&ctx.setOpsSessionClosed;
    const repairPlayNotification=ctx&&ctx.repairPlayNotification;
    const startProjectPlay=ctx&&ctx.startProjectPlay;
    const showProjectPlayConfig=ctx&&ctx.showProjectPlayConfig;
    const closeProjectPlayConfig=ctx&&ctx.closeProjectPlayConfig;
    const refreshProjectGitStatus=ctx&&ctx.refreshProjectGitStatus;
    const loadProjectDependencyStatus=ctx&&ctx.loadProjectDependencyStatus;
    const scanProjectInodes=ctx&&ctx.scanProjectInodes;
    const setProjectActivity=ctx&&ctx.setProjectActivity;
    const installProjectDependencies=ctx&&ctx.installProjectDependencies;
    const cleanupProjectNodeModules=ctx&&ctx.cleanupProjectNodeModules;
    const startGitConflictResolution=ctx&&ctx.startGitConflictResolution;
    const executeProjectGitOperation=ctx&&ctx.executeProjectGitOperation;
    const loadProjectGatherReports=ctx&&ctx.loadProjectGatherReports;
    const loadProjectReviewRequests=ctx&&ctx.loadProjectReviewRequests;
    const loadProjectDeployment=ctx&&ctx.loadProjectDeployment;
    const scaffoldProjectDeployment=ctx&&ctx.scaffoldProjectDeployment;
    const recordProjectDeployment=ctx&&ctx.recordProjectDeployment;
    const executeProjectDeployment=ctx&&ctx.executeProjectDeployment;
    const loadProjectDatabase=ctx&&ctx.loadProjectDatabase;
    const testProjectDatabase=ctx&&ctx.testProjectDatabase;
    const inspectProjectDatabase=ctx&&ctx.inspectProjectDatabase;
    const captureProjectRuntimeSnapshot=ctx&&ctx.captureProjectRuntimeSnapshot;
    const captureProjectRuntimeScreenshot=ctx&&ctx.captureProjectRuntimeScreenshot;
    const restartProjectPlay=ctx&&ctx.restartProjectPlay;
    const stopProjectPlay=ctx&&ctx.stopProjectPlay;
    const openProjectPlay=ctx&&ctx.openProjectPlay;
    const showProjectPlayLogs=ctx&&ctx.showProjectPlayLogs;
    const openPlayNotification=ctx&&ctx.openPlayNotification;
    const openNotificationTarget=ctx&&ctx.openNotificationTarget;
    const dismissNotification=ctx&&ctx.dismissNotification;
    const respondNotification=ctx&&ctx.respondNotification;
    const respondRunRequest=ctx&&ctx.respondRunRequest;
    const resolvedTaskSession=ctx&&ctx.resolvedTaskSession;
    const sessionRefValue=ctx&&ctx.sessionRefValue;
    const AgentBridgeRef=ctx&&ctx.AgentBridge;
    const refreshOpsSessions=ctx&&ctx.refreshOpsSessions;
    const api=ctx&&ctx.api;
    const projectUrl=ctx&&ctx.projectUrl;
    const showConfirmDialog=ctx&&ctx.showConfirmDialog;
    const createRunArtifact=ctx&&ctx.createRunArtifact;
    const saveProjectPlayConfig=ctx&&ctx.saveProjectPlayConfig;
    const createQuickTask=ctx&&ctx.createQuickTask;
    const createAutoApprovalRule=ctx&&ctx.createAutoApprovalRule;
    const saveProjectSettings=ctx&&ctx.saveProjectSettings;
    const splitList=ctx&&ctx.splitList;
    const splitImageRefs=ctx&&ctx.splitImageRefs;
    if(
      !OPS
      || typeof root!=='function'
      || typeof showError!=='function'
      || typeof setBusy!=='function'
      || typeof handleHomeAction!=='function'
      || !AgentBridgeRef
      || typeof api!=='function'
      || typeof projectUrl!=='function'
      || typeof showConfirmDialog!=='function'
      || typeof splitList!=='function'
      || typeof splitImageRefs!=='function'
    ){
      return {};
    }

    async function handleClick(event){
      const btn=event.target.closest('[data-ops-action]');
      if(!btn||!root()||!root().contains(btn))return;
      const action=btn.dataset.opsAction;
      const projectId=btn.dataset.projectId;
      const taskId=btn.dataset.taskId;
      const epicId=btn.dataset.epicId;
      const sessionId=btn.dataset.sessionKey||btn.dataset.sessionId;
      const runId=btn.dataset.runId;
      const notificationId=btn.dataset.notificationId;
      const pushSubscriptionId=btn.dataset.pushSubscriptionId;
      const githubOwner=btn.dataset.githubOwner;
      const githubRepo=btn.dataset.githubRepo;
      const githubBranch=btn.dataset.githubBranch;
      try{
        if(action==='open-projects')return await openProjects();
        if(action==='back-home')return openOpsDashboard();
        const homeActionResult=await handleHomeAction(action,btn);
        if(homeActionResult!==false)return homeActionResult;
        if(action==='refresh-migration-health')return await loadMigrationHealth();
        if(action==='refresh-artifact-health')return await loadArtifactHealth();
        if(action==='scan-stale-runs')return await scanStaleRuns();
        if(action==='refresh-notification-diagnostics')return await loadNotificationDiagnostics();
        if(action==='toggle-notification-setting')return await toggleNotificationSetting(btn.dataset.settingKey);
        if(action==='clear-notification-logs')return await clearNotificationLogs();
        if(action==='delete-push-subscription')return await deletePushSubscription(pushSubscriptionId);
        if(action==='subscribe-browser-push')return await subscribeBrowserPush();
        if(action==='unsubscribe-browser-push')return await unsubscribeBrowserPush();
        if(action==='send-test-push')return await sendTestPushNotification();
        if(action==='toggle-auto-approval-policy')return await toggleAutoApprovalPolicy();
        if(action==='delete-auto-approval-rule')return await deleteAutoApprovalRule(btn.dataset.autoApprovalRuleId);
        if(action==='refresh-database')return await loadDatabaseSettings();
        if(action==='inspect-database')return await inspectDatabaseTables();
        if(action==='refresh-projects'){await loadProjects();return renderProjects();}
        if(action==='refresh-github-status')return await loadGitHubStatus();
        if(action==='list-github-branches')return await loadGitHubBranches(githubOwner,githubRepo);
        if(action==='import-github-repo')return await importGitHubRepository(githubOwner,githubRepo,githubBranch);
        if(action==='show-create'){OPS.showCreate=true;return renderProjects();}
        if(action==='cancel-create'){OPS.showCreate=false;return renderProjects();}
        if(action==='open-project')return await openProjectDetail(projectId);
        if(action==='back-projects')return await openProjects();
        if(action==='refresh-detail')return await refreshDetail();
        if(action==='delete-project')return await deleteProject(projectId);
        if(action==='show-active'){setTaskFilterStatus('active');return renderProjectDetail();}
        if(action==='show-archived'){setTaskFilterStatus('archived');return renderProjectDetail();}
        if(action==='execute-ready-tasks'){
          if(!OPS.currentProject)return null;
          return await executeReadyTasksWithAi(OPS.currentProject.id);
        }
        if(action==='toggle-epic'){
          if(!OPS.currentProject)return null;
          setEpicCollapsed(OPS.currentProject.id,epicId,!isEpicCollapsed(OPS.currentProject.id,epicId));
          return renderProjectDetail();
        }
        if(action==='toggle-task-create'){OPS.taskCreateCollapsed=!OPS.taskCreateCollapsed;return renderProjectDetail();}
        if(action==='toggle-task-filters'){OPS.taskFiltersCollapsed=!OPS.taskFiltersCollapsed;return renderProjectDetail();}
        if(action==='task-primary'){
          const mode=btn.dataset.taskMode||'execute';
          if(mode==='open-session'){
            const sid=String(btn.dataset.sessionKey||btn.dataset.sessionId||'').trim();
            if(sid)return await openOpsSession(sid);
            return showToast('No session linked to this task yet.',2600);
          }
          if(mode==='new-session'||mode==='execute')return await executeTask(taskId);
          return null;
        }
        if(action==='task-needs-more-work')return await markTaskNeedsMoreWork(taskId);
        if(action==='set-task-status-filter'){setTaskFilterStatus(btn.dataset.filterStatus);return renderProjectDetail();}
        if(action==='reset-task-filters'){resetTaskFilters();return renderProjectDetail();}
        if(action==='cancel-edit'){OPS.editingTask=null;OPS.taskFormDraft=null;return renderProjectDetail();}
        if(action==='edit-task'){OPS.editingTask=findTask(taskId);OPS.taskFormDraft=null;OPS.taskCreateCollapsed=false;return renderProjectDetail();}
        if(action==='upload-task-image')return await uploadTaskImage(taskId);
        if(action==='new-chat')return await newChatInProject(projectId?findProject(projectId):null);
        if(action==='open-session')return await openOpsSession(sessionId);
        if(action==='open-run-target')return await openRunTarget(runId);
        if(action==='open-run-detail')return await openRunDetail(runId);
        if(action==='refresh-run-detail')return await openRunDetail(runId||OPS.selectedRunId);
        if(action==='close-run-detail')return closeRunDetail();
        if(action==='set-run-status')return await setRunStatus(runId||OPS.selectedRunId,btn.dataset.runStatus);
        if(action==='complete-run')return await completeRun(runId||OPS.selectedRunId,btn.dataset.runCompletionStatus);
        if(action==='close-session')return await setOpsSessionClosed(sessionId,true,projectId);
        if(action==='git-noop')return null;
        if(action==='repair-play-notification')return await repairPlayNotification(notificationId);
        if(action==='start-play')return await startProjectPlay(projectId);
        if(action==='show-play-config')return await showProjectPlayConfig(projectId);
        if(action==='close-play-config')return closeProjectPlayConfig();
        if(action==='reload-play-config'){delete OPS.playConfigByProject[projectId];return await showProjectPlayConfig(projectId);}
        if(action==='refresh-git-status')return await refreshProjectGitStatus(projectId);
        if(action==='refresh-project-health')return await loadProjectDependencyStatus(projectId);
        if(action==='scan-project-inodes')return await scanProjectInodes(projectId);
        if(action==='toggle-project-activity')return await setProjectActivity(projectId,btn.dataset.projectActive==='true');
        if(action==='install-project-dependencies')return await installProjectDependencies(projectId);
        if(action==='cleanup-project-inodes')return await cleanupProjectNodeModules(projectId);
        if(action==='git-fix-conflicts')return await startGitConflictResolution(projectId);
        if(action==='git-push-execute')return await executeProjectGitOperation(projectId,'push');
        if(action==='git-sync-execute')return await executeProjectGitOperation(projectId,'sync');
        if(action==='refresh-gather-reports')return await loadProjectGatherReports(projectId);
        if(action==='refresh-review-requests')return await loadProjectReviewRequests(projectId);
        if(action==='refresh-deployment')return await loadProjectDeployment(projectId);
        if(action==='scaffold-deployment')return await scaffoldProjectDeployment(projectId);
        if(action==='record-deployment')return await recordProjectDeployment(projectId,btn.dataset.deploymentAction||'deploy');
        if(action==='execute-deployment')return await executeProjectDeployment(projectId,btn.dataset.deploymentAction||'deploy');
        if(action==='refresh-project-database')return await loadProjectDatabase(projectId);
        if(action==='test-project-database')return await testProjectDatabase(projectId);
        if(action==='inspect-project-database')return await inspectProjectDatabase(projectId);
        if(action==='snapshot-play')return await captureProjectRuntimeSnapshot(projectId);
        if(action==='screenshot-play')return await captureProjectRuntimeScreenshot(projectId);
        if(action==='restart-play')return await restartProjectPlay(projectId);
        if(action==='stop-play')return await stopProjectPlay(projectId);
        if(action==='open-play')return openProjectPlay(projectId);
        if(action==='show-play-logs')return await showProjectPlayLogs(projectId);
        if(action==='open-play-notification')return openPlayNotification(notificationId);
        if(action==='open-notification-target')return await openNotificationTarget(notificationId);
        if(action==='dismiss-notification')return await dismissNotification(notificationId);
        if(action==='respond-notification'){
          if(btn.dataset.choice)return await respondNotification(notificationId,{choice:btn.dataset.choice});
          if(btn.dataset.response)return await respondNotification(notificationId,{response:btn.dataset.response});
        }
        if(action==='respond-run-request'){
          const requestId=btn.dataset.runRequestId;
          if(btn.dataset.choice)return await respondRunRequest(requestId,{choice:btn.dataset.choice});
          if(btn.dataset.response)return await respondRunRequest(requestId,{response:btn.dataset.response});
        }
        if(action==='open-task-session'){
          const match=findTask(taskId);
          const session=match&&OPS.currentProject?resolvedTaskSession(match.task,OPS.currentProject.id):null;
          if(session&&sessionRefValue(session))return await openOpsSession(sessionRefValue(session));
          return showToast('No session linked to this task yet.',2600);
        }
        if(action==='execute-task')return await executeTask(taskId);
        if(action==='complete-task'){
          await AgentBridgeRef.sessions.completeTask(OPS.currentProject.id,taskId,{});
          await refreshOpsSessions().catch(()=>OPS.sessions||[]);
          return await refreshDetail();
        }
        if(action==='archive-completed'){
          await api(projectUrl(OPS.currentProject.id,'/tasks/archive-completed'),{method:'POST',body:JSON.stringify({})});
          setTaskFilterStatus('archived');
          return await refreshDetail();
        }
        if(action==='delete-task'){
          const ok=await showConfirmDialog({title:'Delete task',message:'This removes the task from the shared project task file.',confirmLabel:'Delete',danger:true,focusCancel:true});
          if(!ok)return;
          await api(projectUrl(OPS.currentProject.id,`/tasks/${encodeURIComponent(taskId)}/delete`),{method:'POST',body:JSON.stringify({})});
          return await refreshDetail();
        }
        if(action==='delete-epic'){
          const ok=await showConfirmDialog({title:'Delete epic',message:'This removes the epic and its tasks from the shared project task file.',confirmLabel:'Delete',danger:true,focusCancel:true});
          if(!ok)return;
          await api(projectUrl(OPS.currentProject.id,`/epics/${encodeURIComponent(epicId)}/delete`),{method:'POST',body:JSON.stringify({})});
          return await refreshDetail();
        }
      }catch(err){
        showError(err);
      }
    }

    async function handleSubmit(event){
      const form=event.target.closest('[data-ops-submit]');
      if(!form||!root()||!root().contains(form))return;
      event.preventDefault();
      const kind=form.dataset.opsSubmit;
      const data=Object.fromEntries(new FormData(form).entries());
      const useGlobalBusy=kind!=='quick-task'&&kind!=='notification-response'&&kind!=='run-request-response'&&kind!=='github-search'&&kind!=='auto-approval-rule';
      if(useGlobalBusy)setBusy(true);
      try{
        if(kind==='notification-response'){
          await respondNotification(form.dataset.notificationId,{response:data.response});
          return;
        }
        if(kind==='run-request-response'){
          await respondRunRequest(form.dataset.runRequestId,{response:data.response});
          return;
        }
        if(kind==='run-artifact'){
          await createRunArtifact(form.dataset.runId||OPS.selectedRunId,data);
          form.reset();
          return;
        }
        if(kind==='play-config'){
          await saveProjectPlayConfig(form.dataset.projectId,data.content);
          return;
        }
        if(kind==='quick-task'){
          OPS.quickTaskProjectId=String(data.projectId||'').trim();
          OPS.quickTaskText=String(data.text||'');
          OPS.quickTaskGoalMode=data.goalMode==='on';
          await createQuickTask(OPS.quickTaskProjectId,OPS.quickTaskText);
          return;
        }
        if(kind==='auto-approval-rule'){
          await createAutoApprovalRule(data);
          form.reset();
          return;
        }
        if(kind==='github-search'){
          await searchGitHubRepositories(data.query);
          return;
        }
        if(kind==='create-project'){
          const body={name:data.name,path:data.path,coreBranch:data.coreBranch||'main'};
          if(data.profile)body.profile=data.profile;
          const res=await api('/api/ops/projects',{method:'POST',body:JSON.stringify(body)});
          OPS.showCreate=false;
          await loadProjects();
          showToast('Project created',2600);
          return await openProjectDetail(res.project.id);
        }
        if(kind==='project-settings'){
          const projectId=form.dataset.projectId||OPS.currentProject&&OPS.currentProject.id;
          await saveProjectSettings(projectId,data);
          return await refreshDetail();
        }
        if(kind==='create-epic'){
          await api(projectUrl(OPS.currentProject.id,'/epics'),{method:'POST',body:JSON.stringify({title:data.title})});
          OPS.createEpicDraftTitle='';
          return await refreshDetail();
        }
        if(kind==='save-task'){
          const body={
            text:data.text,
            epicId:data.epicId,
            grade:data.grade,
            flags:splitList(data.flags),
            markers:splitList(data.markers),
            images:splitImageRefs(data.images),
          };
          if(data.taskId){
            await api(projectUrl(OPS.currentProject.id,`/tasks/${encodeURIComponent(data.taskId)}`),{method:'POST',body:JSON.stringify(body)});
            OPS.editingTask=null;
          }else{
            const created=await api(projectUrl(OPS.currentProject.id,'/tasks'),{method:'POST',body:JSON.stringify(body)});
            if(data.goalMode==='on'&&created&&created.task&&created.task.id){
              OPS.taskFormDraft=null;
              await refreshDetail();
              await executeTask(created.task.id,{goalMode:true});
              return;
            }
          }
          OPS.taskFormDraft=null;
          return await refreshDetail();
        }
      }catch(err){
        showError(err);
      }finally{
        if(useGlobalBusy)setBusy(false);
      }
    }

    return {handleClick,handleSubmit};
  }

  window.HermesOpsModules.dashboardActions={bindDashboard};
})();

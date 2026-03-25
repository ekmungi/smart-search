; NSIS hooks for Smart Search installer.
; Manages process cleanup, MCP registration, and data deletion.

!macro NSIS_HOOK_PREINSTALL
  ; Check if Smart Search processes are running before overwriting files.
  ; Without this, Windows shows "abort, retry, cancel" when the exe is locked.
  nsExec::ExecToStack 'cmd /C tasklist /FI "IMAGENAME eq smart-search.exe" /NH | findstr /I "smart-search.exe"'
  Pop $0
  Pop $1
  ${If} $0 == 0
    MessageBox MB_YESNO "Smart Search is currently running.$\r$\n$\r$\nClose it to continue installation?" IDYES _kill_sidecar
    Abort
    _kill_sidecar:
    nsExec::ExecToLog 'taskkill /F /IM smart-search.exe'
    nsExec::ExecToLog 'taskkill /F /IM "Smart Search.exe"'
    Sleep 1000
  ${Else}
    ; Sidecar not found, but the main app might still be running
    nsExec::ExecToStack 'cmd /C tasklist /FI "IMAGENAME eq Smart Search.exe" /NH | findstr /I "Smart Search.exe"'
    Pop $0
    Pop $1
    ${If} $0 == 0
      MessageBox MB_YESNO "Smart Search is currently running.$\r$\n$\r$\nClose it to continue installation?" IDYES _kill_app
      Abort
      _kill_app:
      nsExec::ExecToLog 'taskkill /F /IM "Smart Search.exe"'
      Sleep 1000
    ${EndIf}
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  ; Kill any running smart-search processes before file deletion.
  ; Without this, Windows cannot delete the exe if the sidecar is still running.
  nsExec::ExecToLog 'taskkill /F /IM smart-search.exe'
  nsExec::ExecToLog 'taskkill /F /IM "Smart Search.exe"'
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ; Deregister any stale MCP entry, then register with the current install path.
  ; Uses /TIMEOUT=5000 to avoid hanging the installer if claude CLI is slow.
  DetailPrint "Registering Smart Search MCP server..."
  nsExec::ExecToLog 'claude mcp remove -s user smart-search'
  nsExec::ExecToLog 'claude mcp add -s user smart-search -- "$INSTDIR\smart-search.exe" mcp'
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Clean up MCP registration on uninstall.
  nsExec::ExecToLog 'claude mcp remove -s user smart-search'

  ; Delete actual app data directory.
  ; Tauri's built-in cleanup targets $LOCALAPPDATA\com.smartsearch.desktop (bundle ID),
  ; but the Python backend stores data at $LOCALAPPDATA\smart-search.
  ${If} $DeleteAppDataCheckboxState = 1
  ${AndIf} $UpdateMode <> 1
    RmDir /r "$LOCALAPPDATA\smart-search"
  ${EndIf}
!macroend

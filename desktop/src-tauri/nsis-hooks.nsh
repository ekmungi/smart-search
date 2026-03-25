; NSIS hooks for Smart Search installer.
; Manages MCP registration and process cleanup for install/uninstall.

!macro NSIS_HOOK_PREUNINSTALL
  ; Kill any running smart-search processes before file deletion.
  ; Without this, Windows cannot delete the exe if the sidecar is still running.
  nsExec::ExecToLog 'taskkill /F /IM smart-search.exe'
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

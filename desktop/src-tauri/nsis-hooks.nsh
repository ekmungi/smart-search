; NSIS hooks for Smart Search installer.
; Manages MCP registration so the claude CLI always points to the correct sidecar path.

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
!macroend

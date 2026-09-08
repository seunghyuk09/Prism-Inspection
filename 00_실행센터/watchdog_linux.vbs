' ===================================================================
' Prism (Linux/WSL) watchdog - one pass. ASCII only, no encoding issues.
'   1) Web port 10500 down  -> run start_wsl.vbs  (systemd brings up db+app)
'   2) cloudflared missing  -> run start_tunnel.vbs
' Paths are resolved from this script's folder, so nothing is hardcoded.
' Safe to run repeatedly.
' ===================================================================
Option Explicit
Dim sh, fso, q, here, chk, up, svc, col, p, running

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
q = Chr(34)
here = fso.GetParentFolderName(WScript.ScriptFullName)
chk = sh.ExpandEnvironmentStrings("%TEMP%\prism_linux_chk.txt")

' --- 1) web server (WSL + prism.service) -----------------------------
sh.Run "cmd /c netstat -ano | findstr LISTENING | findstr " & q & ":10500" & q & " > " & q & chk & q, 0, True

up = False
If fso.FileExists(chk) Then
  If fso.GetFile(chk).Size > 0 Then up = True
End If

If Not up Then
  If fso.FileExists(here & "\start_wsl.vbs") Then
    sh.Run "wscript " & q & here & "\start_wsl.vbs" & q, 0, True
  End If
End If

' --- 2) cloudflare tunnel --------------------------------------------
running = False
On Error Resume Next
Set svc = GetObject("winmgmts:\\.\root\cimv2")
Set col = svc.ExecQuery("SELECT ProcessId FROM Win32_Process WHERE Name='cloudflared.exe'")
For Each p In col
  running = True
Next
On Error GoTo 0

If Not running Then
  If fso.FileExists(here & "\start_tunnel.vbs") Then
    sh.Run "wscript " & q & here & "\start_tunnel.vbs" & q, 0, True
  End If
End If

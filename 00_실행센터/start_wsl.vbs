' ===================================================================
' Start WSL (Ubuntu) and KEEP IT ALIVE. ASCII only - no encoding issues.
'
'   WSL2 shuts the VM down when no client session is attached, even with
'   systemd running. Booting once is NOT enough - the VM dies in ~20s and
'   the web service goes down with it (observed 2026-09-09).
'   So we hold one long-lived session open: "wsl -e sleep infinity".
'   While that wsl.exe process lives, the VM stays up and systemd keeps
'   postgresql + prism running.
'
'   - Distro from PRISM_WSL_DISTRO env var, default "Ubuntu".
'   - Safe to run repeatedly: if a keepalive already exists, do nothing.
' ===================================================================
Option Explicit
Dim sh, svc, col, p, distro, alive

Set sh = CreateObject("WScript.Shell")

distro = sh.ExpandEnvironmentStrings("%PRISM_WSL_DISTRO%")
If distro = "" Or InStr(distro, "%") > 0 Then distro = "Ubuntu"

' already holding a session? (wsl.exe running "sleep infinity")
alive = False
On Error Resume Next
Set svc = GetObject("winmgmts:")
Set col = svc.ExecQuery("SELECT CommandLine FROM Win32_Process WHERE Name='wsl.exe'")
For Each p In col
  If InStr(LCase(p.CommandLine & ""), "sleep infinity") > 0 Then alive = True
Next
On Error GoTo 0

If Not alive Then
  ' 0 = hidden, False = do not wait (this process must stay alive)
  sh.Run "wsl.exe -d " & distro & " -e sleep infinity", 0, False
End If

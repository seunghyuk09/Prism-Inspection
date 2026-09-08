' ===================================================================
' Start WSL (Ubuntu) silently at logon (ASCII only - no encoding issues).
'   - Booting WSL makes systemd start postgresql + prism automatically.
'   - Distro name is read from PRISM_WSL_DISTRO env var, default "Ubuntu".
'   - Safe to run repeatedly: if WSL is already up, this is a no-op.
' ===================================================================
Option Explicit
Dim sh, distro
Set sh = CreateObject("WScript.Shell")

distro = sh.ExpandEnvironmentStrings("%PRISM_WSL_DISTRO%")
If distro = "" Or InStr(distro, "%") > 0 Then distro = "Ubuntu"

' Boot the distro. systemd inside WSL brings up the enabled services.
sh.Run "wsl.exe -d " & distro & " -e /bin/true", 0, True

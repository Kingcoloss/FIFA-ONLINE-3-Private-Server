// Replacement for the Garena fifalauncher.exe (Themida-packed; its Garena SSO / version
// servers are dead). Does what the original does at the end of its flow: start fifazf.exe
// with server args and stay alive, because the game is handed the launcher PID.
// Anti-cheat is untouched: fifazf.exe still runs its own XignCode/HackShield init.
//
// Build: C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe /nologo /target:winexe /out:fifalauncher.exe fifalauncher.cs
// Run:   fifalauncher.exe                     -> local defaults below (same as launch_game.ps1)
//        fifalauncher.exe -QUICKMATCH/... ... -> those args instead of the defaults
// fifazf.exe is looked up next to this exe, then in FO3_GAME (default: the 3Sea client folder;
// FO3_CLIENT=fo3id: D:\FO3ID\32795). FO3_LAUNCH_REGION sets `region <code>` (3Sea: th, FO3 ID: id),
// as fo3conf.py does for the server. The game folder is only read, never written.
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Windows.Forms;

static class Launcher
{
    static string Env(string name, string fallback)
    {
        string v = Environment.GetEnvironmentVariable(name);
        return string.IsNullOrWhiteSpace(v) ? fallback : v.Trim();
    }

    static readonly bool Fo3Id = Env("FO3_CLIENT", "3sea").ToLowerInvariant() == "fo3id";
    static readonly string GameDir = Env("FO3_GAME", Fo3Id ? @"D:\FO3ID\32795" : @"F:\FOServer\3Sea FIFA Online 3");
    static readonly string Region = Env("FO3_LAUNCH_REGION", Fo3Id ? "id" : "th").ToLowerInvariant();
    static readonly string Defaults =
        "-QUICKMATCH/SERVER=127.0.0.1:28000 -QUICKMATCH/PROTOCOL=tcp " +
        "-QUICKMATCH/NOTISERVER=127.0.0.1:28001 -PUBLISHER/GARENA/TOKEN=testtoken " +
        "-LOCALE/PUBLISHING_REGION=" + Region.ToUpperInvariant() + " -DUMPTRUCK/SERVER=127.0.0.1 " +
        // Alias pairs (no dash) select the Garena login path; see launch_game.ps1.
        "region " + Region + " token testtoken";

    [STAThread]
    static int Main(string[] args)
    {
        string exe = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "fifazf.exe");
        if (!File.Exists(exe))
            exe = Path.Combine(GameDir, "fifazf.exe");

        string gameArgs = args.Length == 0
            ? Defaults
            : string.Join(" ", args.Select(a => a.Contains(" ") ? "\"" + a + "\"" : a));
        gameArgs += " -FIFA/LAUNCHER/PID=" + Process.GetCurrentProcess().Id;

        // ShellExecute so fifazf.exe's requireAdministrator manifest gets its UAC prompt.
        var psi = new ProcessStartInfo(exe, gameArgs)
        {
            WorkingDirectory = Path.GetDirectoryName(exe),
            UseShellExecute = true,
        };
        try
        {
            using (var game = Process.Start(psi))
            {
                game.WaitForExit();
                return game.ExitCode;
            }
        }
        catch (Exception e)
        {
            MessageBox.Show(exe + "\n\n" + e.Message, "fifalauncher", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}

// Replacement for the Garena fifalauncher.exe (Themida-packed; its Garena SSO / version
// servers are dead). Does what the original does at the end of its flow: start fifazf.exe
// with server args and stay alive, because the game is handed the launcher PID.
// Anti-cheat is untouched: fifazf.exe still runs its own XignCode/HackShield init.
//
// Build: C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe /nologo /target:winexe /out:fifalauncher.exe fifalauncher.cs
// Run:   fifalauncher.exe                     -> local defaults below (same as launch_game.ps1)
//        fifalauncher.exe -QUICKMATCH/... ... -> those args instead of the defaults
// The client is found as fo3conf.py finds it, so one build works on any PC: fifazf.exe next to
// this exe, else FO3_GAME / FO3_CLIENT / FO3_LAUNCH_REGION from the environment (play.bat sets
// them from `python fo3conf.py env`), else from fo3.local.env in the repository folder, else the
// profiles' usual folders. The client kind comes from the folder when FO3_CLIENT is not set
// (loose LANGUAGESTRING_THA.json: 3Sea, region th; fo3id.version: FO3 ID, region id).
// The game folder is only read, never written.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Windows.Forms;

static class Launcher
{
    static readonly string Here = AppDomain.CurrentDomain.BaseDirectory;
    static readonly Dictionary<string, string> Local = ReadLocal();

    static Dictionary<string, string> ReadLocal()
    {
        var d = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (string dir in new[] { Path.Combine(Here, ".."), Here })
        {
            string f = Path.Combine(dir, "fo3.local.env");
            if (!File.Exists(f)) continue;
            foreach (string raw in File.ReadAllLines(f))
            {
                string line = raw.Trim();
                int eq = line.IndexOf('=');
                if (line.Length == 0 || line[0] == '#' || eq < 1) continue;
                d[line.Substring(0, eq).Trim()] = line.Substring(eq + 1).Trim().Trim('"');
            }
            break;
        }
        return d;
    }

    static string Setting(string name)
    {
        string v = Environment.GetEnvironmentVariable(name);
        if (string.IsNullOrWhiteSpace(v)) Local.TryGetValue(name, out v);
        return string.IsNullOrWhiteSpace(v) ? null : v.Trim();
    }

    static bool IsClient(string dir)
    {
        return !string.IsNullOrEmpty(dir) && File.Exists(Path.Combine(dir, "fifazf.exe"));
    }

    static string DetectClient(string dir)
    {
        if (File.Exists(Path.Combine(dir, @"data\ui\external\LANGUAGESTRING_THA.json"))) return "3sea";
        if (File.Exists(Path.Combine(dir, "fo3id.version")) || Directory.Exists(Path.Combine(dir, @"_cache\games\fo3id")))
            return "fo3id";
        return "3sea";
    }

    static string FindGame(string client)
    {
        var order = new List<string> { Here, Setting("FO3_GAME") };
        if (client == "fo3id") order.Add(@"D:\FO3ID\32795");
        order.Add(@"F:\FOServer\3Sea FIFA Online 3");
        order.Add(@"D:\FO3ID\32795");
        return order.FirstOrDefault(IsClient);
    }

    [STAThread]
    static int Main(string[] args)
    {
        string client = (Setting("FO3_CLIENT") ?? "").ToLowerInvariant();
        string game = FindGame(client);
        if (game == null)
        {
            MessageBox.Show("No fifazf.exe found. Run play.bat, or `python fo3conf.py set <client folder>` once.",
                "fifalauncher", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        if (client == "") client = DetectClient(game);
        string region = (Setting("FO3_LAUNCH_REGION") ?? (client == "fo3id" ? "id" : "th")).ToLowerInvariant();
        string defaults =
            "-QUICKMATCH/SERVER=127.0.0.1:28000 -QUICKMATCH/PROTOCOL=tcp " +
            "-QUICKMATCH/NOTISERVER=127.0.0.1:28001 -PUBLISHER/GARENA/TOKEN=testtoken " +
            "-LOCALE/PUBLISHING_REGION=" + region.ToUpperInvariant() + " -DUMPTRUCK/SERVER=127.0.0.1 " +
            // Alias pairs (no dash) select the Garena login path; see launch_game.ps1.
            "region " + region + " token testtoken";

        string exe = Path.Combine(game, "fifazf.exe");
        string gameArgs = args.Length == 0
            ? defaults
            : string.Join(" ", args.Select(a => a.Contains(" ") ? "\"" + a + "\"" : a));
        gameArgs += " -FIFA/LAUNCHER/PID=" + Process.GetCurrentProcess().Id;

        // ShellExecute so fifazf.exe's requireAdministrator manifest gets its UAC prompt.
        var psi = new ProcessStartInfo(exe, gameArgs)
        {
            WorkingDirectory = game,
            UseShellExecute = true,
        };
        try
        {
            using (var proc = Process.Start(psi))
            {
                proc.WaitForExit();
                return proc.ExitCode;
            }
        }
        catch (Exception e)
        {
            MessageBox.Show(exe + "\n\n" + e.Message, "fifalauncher", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}

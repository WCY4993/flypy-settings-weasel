// Small per-user logon launcher. Never restart an already-running Weasel.
using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using Microsoft.Win32;

internal static class WeaselStartup {
    static readonly Stopwatch Clock = Stopwatch.StartNew();
    static void Log(string stage) {
        try {
            string folder = AppDomain.CurrentDomain.BaseDirectory;
            Directory.CreateDirectory(folder);
            string file = Path.Combine(folder, "startup-status.log");
            if (File.Exists(file) && new FileInfo(file).Length > 32768) File.WriteAllText(file, "");
            File.AppendAllText(file, DateTimeOffset.Now.ToString("o") + "\t" + Clock.ElapsedMilliseconds + "\t" + stage + Environment.NewLine);
        } catch { /* Logging must never prevent startup. No typed text is logged. */ }
    }
    static bool Running() {
        int session = Process.GetCurrentProcess().SessionId;
        foreach (Process process in Process.GetProcessesByName("WeaselServer")) {
            using (process) {
                try { if (process.SessionId == session && !process.HasExited) return true; }
                catch (InvalidOperationException) { }
                catch (System.ComponentModel.Win32Exception) { }
            }
        }
        return false;
    }
    static string ResolveServer() {
        foreach (RegistryView view in new[] {RegistryView.Registry32, RegistryView.Registry64}) {
            using (RegistryKey machine = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, view))
            using (RegistryKey key = machine.OpenSubKey(@"SOFTWARE\Rime\Weasel")) {
                string folder = key == null ? null : key.GetValue("WeaselRoot") as string;
                if (!String.IsNullOrEmpty(folder)) {
                    string file = Path.Combine(folder, "WeaselServer.exe");
                    if (File.Exists(file)) return file;
                }
            }
        }
        throw new FileNotFoundException("Weasel installation was not found.");
    }
    [STAThread]
    static int Main(string[] args) {
        bool owned;
        using (Mutex mutex = new Mutex(true, @"Local\FlypySettings.WeaselStartup", out owned)) {
            if (!owned) return 0;
            try {
                Log("launcher-start");
                if (Running()) { Log("already-running"); return 0; }
                string server = ResolveServer();
                if (args.Length == 1 && args[0] == "--check") { Log("check-ok"); return 0; }
                if (Running()) { Log("already-running"); return 0; }
                ProcessStartInfo info = new ProcessStartInfo(server);
                info.WorkingDirectory = Path.GetDirectoryName(server);
                info.UseShellExecute = false;
                info.CreateNoWindow = true;
                using (Process process = Process.Start(info)) {
                    Log("server-started");
                }
                return 0;
            } catch (Exception error) {
                Log("error:" + error.GetType().Name);
                return 1;
            } finally { mutex.ReleaseMutex(); }
        }
    }
}

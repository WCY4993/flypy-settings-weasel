// Small per-user logon launcher. Never restart an already-running Weasel.
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Threading;
using Microsoft.Win32;

internal static class WeaselStartup {
    static readonly object LogLock = new object();
    static readonly Stopwatch Clock = Stopwatch.StartNew();
    static void Log(string stage) {
        try { lock (LogLock) {
            string folder = AppDomain.CurrentDomain.BaseDirectory;
            Directory.CreateDirectory(folder);
            string file = Path.Combine(folder, "startup-status.log");
            if (File.Exists(file) && new FileInfo(file).Length > 32768) File.WriteAllText(file, "");
            File.AppendAllText(file, DateTimeOffset.Now.ToString("o") + "\t" + Clock.ElapsedMilliseconds + "\t" + stage + Environment.NewLine);
        }} catch { /* Logging must never prevent startup. No typed text is logged. */ }
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
    // Echo with session 0 only tests IPC responsiveness. It never creates a session,
    // sends a key, changes focus, or modifies the current composition.
    static bool Responsive(int timeout) {
        try {
            using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", Environment.UserName + @"\WeaselNamedPipe", PipeDirection.InOut, PipeOptions.Asynchronous)) {
                pipe.Connect(timeout);
                pipe.ReadMode = PipeTransmissionMode.Message;
                byte[] request = new byte[12];
                BitConverter.GetBytes(0x8001).CopyTo(request, 0);
                IAsyncResult write = pipe.BeginWrite(request, 0, request.Length, null, null);
                if (!write.AsyncWaitHandle.WaitOne(timeout)) return false;
                pipe.EndWrite(write);
                byte[] reply = new byte[4096];
                IAsyncResult read = pipe.BeginRead(reply, 0, reply.Length, null, null);
                if (!read.AsyncWaitHandle.WaitOne(timeout)) return false;
                return pipe.EndRead(read) >= 4;
            }
        } catch (IOException) { return false; }
          catch (TimeoutException) { return false; }
          catch (UnauthorizedAccessException) { return false; }
    }
    static void ProbeDataPath() {
        try {
            using (RegistryKey key = Registry.CurrentUser.OpenSubKey(@"Software\Rime\Weasel")) {
                string root = key == null ? null : key.GetValue("RimeUserDir") as string;
                if (String.IsNullOrEmpty(root)) { Log("data-read:default-path"); return; }
                Log("data-read:start");
                // Read only one byte; no content, username or path is written to the log.
                using (FileStream file = new FileStream(Path.Combine(root, "default.yaml"), FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete)) {
                    file.ReadByte();
                }
                Log("data-read:ok");
            }
        } catch (Exception error) { Log("data-read:" + error.GetType().Name); }
    }
    static bool WaitForResponse(int milliseconds) {
        Stopwatch wait = Stopwatch.StartNew();
        while (wait.ElapsedMilliseconds < milliseconds) {
            if (Responsive(250)) { Log("ipc-responsive"); return true; }
            Thread.Sleep(250);
        }
        Log("ipc-response-timeout");
        return false;
    }
    [STAThread]
    static int Main(string[] args) {
        bool owned;
        using (Mutex mutex = new Mutex(true, @"Local\FlypySettings.WeaselStartup", out owned)) {
            if (!owned) return 0;
            try {
                Log("launcher-start");
                if (args.Length == 1 && args[0] == "--probe") {
                    Thread data = new Thread(ProbeDataPath); data.IsBackground = true; data.Start();
                    bool ready = WaitForResponse(5000); data.Join(1000); return ready ? 0 : 2;
                }
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
                    Thread data = new Thread(ProbeDataPath); data.IsBackground = true; data.Start();
                    WaitForResponse(90000);
                    data.Join(1000);
                }
                return 0;
            } catch (Exception error) {
                Log("error:" + error.GetType().Name);
                return 1;
            } finally { mutex.ReleaseMutex(); }
        }
    }
}

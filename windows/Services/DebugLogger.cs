using System.Diagnostics;
using System.IO;

namespace ProxmoxSpiceManager.Services;

public static class DebugLogger
{
    private static readonly string LogDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "proxmox-spice");

    private static readonly object Lock = new();
    private static StreamWriter? _writer;
    private static long _bytesWritten;
    private const long MaxLogSize = 5 * 1024 * 1024; // 5 MB

    public static bool Enabled { get; private set; }

    public static string LogFilePath => Path.Combine(LogDir, "debug.log");

    public static void SetEnabled(bool enabled)
    {
        if (enabled == Enabled) return;
        Enabled = enabled;

        if (enabled)
        {
            try
            {
                Directory.CreateDirectory(LogDir);
                RotateIfNeeded();
                _writer = new StreamWriter(LogFilePath, append: true) { AutoFlush = true };
                _bytesWritten = new FileInfo(LogFilePath).Length;
                Log("--- Debug logging started ---");
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[DebugLogger] Failed to open log file: {ex.Message}");
                Enabled = false;
            }
        }
        else
        {
            Log("--- Debug logging stopped ---");
            lock (Lock)
            {
                _writer?.Dispose();
                _writer = null;
            }
        }
    }

    private static void RotateIfNeeded()
    {
        try
        {
            if (!File.Exists(LogFilePath)) return;
            if (new FileInfo(LogFilePath).Length < MaxLogSize) return;
            var prev = Path.Combine(LogDir, "debug.prev.log");
            File.Copy(LogFilePath, prev, overwrite: true);
            File.Delete(LogFilePath);
        }
        catch { }
    }

    public static void Log(string message)
    {
        if (!Enabled) return;
        var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff}  {message}";
        lock (Lock)
        {
            try
            {
                _writer?.WriteLine(line);
                _bytesWritten += line.Length + Environment.NewLine.Length;
                if (_bytesWritten >= MaxLogSize)
                {
                    _writer?.Dispose();
                    RotateIfNeeded();
                    _writer = new StreamWriter(LogFilePath, append: true) { AutoFlush = true };
                    _bytesWritten = 0;
                }
            }
            catch { }
        }
    }

    public static Stopwatch StartTimer(string operation)
    {
        Log($"[START] {operation}");
        return Stopwatch.StartNew();
    }

    public static void StopTimer(Stopwatch sw, string operation)
    {
        sw.Stop();
        Log($"[ END ] {operation} ({sw.ElapsedMilliseconds}ms)");
    }
}

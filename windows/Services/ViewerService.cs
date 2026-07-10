using System.Diagnostics;
using System.IO;
using Microsoft.Win32;

namespace ProxmoxSpiceManager.Services;

public static class ViewerService
{
    private static readonly string[] SearchPaths =
    [
        @"C:\Program Files\VirtViewer v11.0-256\bin",
        @"C:\Program Files\VirtViewer\bin",
        @"C:\Program Files (x86)\VirtViewer v11.0-256\bin",
        @"C:\Program Files (x86)\VirtViewer\bin",
    ];

    public static string? FindRemoteViewer()
    {
        // Check PATH
        var pathDirs = Environment.GetEnvironmentVariable("PATH")?.Split(';') ?? [];
        foreach (var dir in pathDirs)
        {
            var candidate = Path.Combine(dir.Trim(), "remote-viewer.exe");
            if (File.Exists(candidate))
                return candidate;
        }

        // Check known install locations
        foreach (var dir in SearchPaths)
        {
            var candidate = Path.Combine(dir, "remote-viewer.exe");
            if (File.Exists(candidate))
                return candidate;
        }

        // Check registry
        try
        {
            foreach (var hive in new[] { RegistryHive.LocalMachine, RegistryHive.CurrentUser })
            foreach (var subkey in new[] { @"SOFTWARE\VirtViewer", @"SOFTWARE\WOW6432Node\VirtViewer" })
            {
                using var baseKey = RegistryKey.OpenBaseKey(hive, RegistryView.Default);
                using var key = baseKey.OpenSubKey(subkey);
                if (key?.GetValue("InstallDir") is string installDir)
                {
                    var candidate = Path.Combine(installDir, "bin", "remote-viewer.exe");
                    if (File.Exists(candidate))
                        return candidate;
                }
            }
        }
        catch { }

        return null;
    }

    public static void LaunchSpice(string viewerPath, string vvFilePath)
    {
        var proc = Process.Start(new ProcessStartInfo
        {
            FileName = viewerPath,
            Arguments = $"\"{vvFilePath}\"",
            UseShellExecute = false,
            CreateNoWindow = true,
        });

        if (proc != null)
        {
            Task.Run(() =>
            {
                proc.WaitForExit();
                try { File.Delete(vvFilePath); } catch { }
            });
        }
    }
}

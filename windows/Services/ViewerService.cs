using System.Diagnostics;
using System.IO;
using Microsoft.Win32;

namespace ProxmoxSpiceManager.Services;

public static class ViewerService
{
    private static string? _cachedViewerPath;

    private static readonly string[] SearchPaths =
    [
        @"C:\Program Files\VirtViewer v11.0-256\bin",
        @"C:\Program Files\VirtViewer\bin",
        @"C:\Program Files (x86)\VirtViewer v11.0-256\bin",
        @"C:\Program Files (x86)\VirtViewer\bin",
    ];

    public static string? FindRemoteViewer()
    {
        if (_cachedViewerPath != null && File.Exists(_cachedViewerPath))
            return _cachedViewerPath;

        // Known install locations and the registry come before PATH, so a
        // remote-viewer.exe dropped in a user-writable PATH folder is not preferred.

        // Check known install locations
        foreach (var dir in SearchPaths)
        {
            var candidate = Path.Combine(dir, "remote-viewer.exe");
            if (File.Exists(candidate))
                return _cachedViewerPath = candidate;
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
                        return _cachedViewerPath = candidate;
                }
            }
        }
        catch { }

        // Check PATH, skipping empty or relative entries, which would resolve
        // against the current directory
        var pathDirs = Environment.GetEnvironmentVariable("PATH")?.Split(';') ?? [];
        foreach (var dir in pathDirs.Select(d => d.Trim()))
        {
            if (!Path.IsPathFullyQualified(dir))
                continue;
            var candidate = Path.Combine(dir, "remote-viewer.exe");
            if (File.Exists(candidate))
                return _cachedViewerPath = candidate;
        }

        return null;
    }

    // Random name and CreateNew, so the file (which holds the SPICE password)
    // cannot be predicted or pre-created. It inherits the per-user %TEMP% ACL.
    public static string WriteVvFile(string content)
    {
        var path = Path.Combine(Path.GetTempPath(), $"pve-spice-{Path.GetRandomFileName()}.vv");
        using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        using var writer = new StreamWriter(stream);
        writer.Write(content);
        return path;
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

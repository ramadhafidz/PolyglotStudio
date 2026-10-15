using System;
using System.IO;
using System.Collections.Generic;
using Trinity.Core.Cache;
using Trinity.Core.Flatbuffers.TR.ResourceDictionary;
using Trinity.Core.Serializers.TR;
using Trinity.Core.Utils;
using TrinityFileExplorer;

namespace TrpfsWorker;

class Program
{
    static CustomFileDescriptor _fileDescriptor;
    static FileSystem _fileSystem;
    static dynamic _extractor;
    static bool _cacheLoaded = false;
    static Dictionary<string, ulong> _pathToHash = new(StringComparer.OrdinalIgnoreCase);

    static void Main(string[] args)
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        Console.WriteLine("TRPFS_WORKER_INIT");

        if (args.Length > 0 && args[0] == "--test")
        {
            Console.WriteLine("Test mode ok");
            return;
        }

        string line;
        while ((line = Console.ReadLine()) != null)
        {
            line = line.Trim();
            if (string.IsNullOrEmpty(line)) continue;

            try
            {
                var parts = line.Split(' ', 2);
                var cmd = parts[0].ToUpperInvariant();
                var arg = parts.Length > 1 ? parts[1] : "";

                switch (cmd)
                {
                    case "LOAD":
                        HandleLoad(arg);
                        break;
                    case "LIST":
                        HandleList(arg);
                        break;
                    case "EXTRACT":
                        HandleExtract(arg);
                        break;
                    case "EXTRACT_PNG":
                        HandleExtractPng(arg);
                        break;
                    case "PING":
                        Console.WriteLine("PONG");
                        break;
                    case "QUIT":
                    case "EXIT":
                        Console.WriteLine("BYE");
                        return;
                    default:
                        Console.WriteLine($"ERR Unknown command: {cmd}");
                        break;
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"ERR {ex.Message}");
            }
        }
    }

    static void EnsureCache(string cachePath = null)
    {
        if (_cacheLoaded) return;
        if (string.IsNullOrEmpty(cachePath))
        {
            var localPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "GFPAKHashCache.bin");
            if (File.Exists(localPath))
            {
                cachePath = localPath;
            }
            else
            {
                cachePath = @"D:\Environtment\utilities\trinity\fileexplorer\GFPAKHashCache.bin";
            }
        }
        if (File.Exists(cachePath))
        {
            GFPakHashCache.Open(cachePath);
            _cacheLoaded = true;
        }
    }

    static void HandleLoad(string romfsDir)
    {
        romfsDir = romfsDir.Trim('"');
        var trpfdPath = Path.Combine(romfsDir, "arc", "data.trpfd");
        var trpfsPath = Path.Combine(romfsDir, "arc", "data.trpfs");

        if (!File.Exists(trpfdPath))
        {
            Console.WriteLine($"ERR TRPFD not found at {trpfdPath}");
            return;
        }
        if (!File.Exists(trpfsPath))
        {
            Console.WriteLine($"ERR TRPFS not found at {trpfsPath}");
            return;
        }

        EnsureCache();

        _fileDescriptor = FlatBufferConverter.DeserializeFrom<CustomFileDescriptor>(trpfdPath);
        _fileSystem = ONEFILESerializer.DeserializeFileSystem(trpfsPath);

        // Reflectively instantiate TrpfsExtractor to avoid accessibility issues
        var extType = typeof(TrinityExplorerWindow).Assembly.GetType("TrinityFileExplorer.TrinityExplorerWindow+TrpfsExtractor");
        _extractor = Activator.CreateInstance(extType, _fileDescriptor, _fileSystem, trpfsPath);

        // Build path to hash map
        _pathToHash.Clear();
        foreach (var h in _fileDescriptor.FileHashes)
        {
            var name = GFPakHashCache.GetName(h);
            if (!string.IsNullOrEmpty(name))
            {
                _pathToHash[name] = h;
            }
        }

        Console.WriteLine($"READY {_fileDescriptor.FileHashes.Length} {_pathToHash.Count}");
    }

    static void HandleList(string filter)
    {
        if (_fileDescriptor == null)
        {
            Console.WriteLine("ERR Not loaded");
            return;
        }

        filter = filter.Trim('"').ToLowerInvariant();

        foreach (var kvp in _pathToHash)
        {
            if (string.IsNullOrEmpty(filter) || kvp.Key.ToLowerInvariant().Contains(filter))
            {
                Console.WriteLine($"{kvp.Value:x16}|{kvp.Key}");
            }
        }
        Console.WriteLine("END_LIST");
    }

    static void HandleExtract(string arg)
    {
        if (_extractor == null)
        {
            Console.WriteLine("ERR Not loaded");
            return;
        }

        var parts = arg.Split(' ', 2);
        var target = parts[0].Trim('"');
        var outPath = parts.Length > 1 ? parts[1].Trim('"') : null;

        ulong hash = 0;
        if (target.StartsWith("0x", StringComparison.OrdinalIgnoreCase))
        {
            hash = Convert.ToUInt64(target.Substring(2), 16);
        }
        else if (ulong.TryParse(target, out var parsedHash))
        {
            hash = parsedHash;
        }
        else if (!_pathToHash.TryGetValue(target, out hash))
        {
            Console.WriteLine($"ERR File path not found in cache: {target}");
            return;
        }

        var extType = _extractor.GetType();
        var tryGetMethod = extType.GetMethod("TryGetFileBytes");
        object[] methodParams = new object[] { hash, null };
        bool success = (bool)tryGetMethod.Invoke(_extractor, methodParams);

        if (!success || methodParams[1] == null)
        {
            Console.WriteLine($"ERR Failed to extract hash: 0x{hash:x16}");
            return;
        }

        byte[] bytes = (byte[])methodParams[1];

        if (!string.IsNullOrEmpty(outPath))
        {
            var dir = Path.GetDirectoryName(outPath);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.WriteAllBytes(outPath, bytes);
            Console.WriteLine($"EXTRACTED {bytes.Length} {outPath}");
        }
        else
        {
            var base64 = Convert.ToBase64String(bytes);
            Console.WriteLine($"BASE64 {bytes.Length} {base64}");
        }
    }

    static void HandleExtractPng(string arg)
    {
        var parts = arg.Split(' ', 2);
        var target = parts[0].Trim('"');
        var outPath = parts.Length > 1 ? parts[1].Trim('"') : null;

        if (string.IsNullOrEmpty(outPath))
        {
            Console.WriteLine("ERR Output path missing for EXTRACT_PNG");
            return;
        }

        byte[] bytes = null;

        if (File.Exists(target))
        {
            try
            {
                bytes = File.ReadAllBytes(target);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"ERR Failed to read local file {target}: {ex.Message}");
                return;
            }
        }
        else
        {
            if (_extractor == null)
            {
                Console.WriteLine("ERR Not loaded");
                return;
            }

            ulong hash = 0;
            if (target.StartsWith("0x", StringComparison.OrdinalIgnoreCase))
            {
                hash = Convert.ToUInt64(target.Substring(2), 16);
            }
            else if (ulong.TryParse(target, out var parsedHash))
            {
                hash = parsedHash;
            }
            else if (!_pathToHash.TryGetValue(target, out hash))
            {
                Console.WriteLine($"ERR File path not found in cache: {target}");
                return;
            }

            var extType = _extractor.GetType();
            var tryGetMethod = extType.GetMethod("TryGetFileBytes");
            object[] methodParams = new object[] { hash, null };
            bool success = (bool)tryGetMethod.Invoke(_extractor, methodParams);

            if (!success || methodParams[1] == null)
            {
                Console.WriteLine($"ERR Failed to extract hash: 0x{hash:x16}");
                return;
            }

            bytes = (byte[])methodParams[1];
        }

        try
        {
            var dir = Path.GetDirectoryName(outPath);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

            // Check if file is BNTX format
            if (bytes.Length >= 8 && bytes[0] == (byte)'B' && bytes[1] == (byte)'N' && bytes[2] == (byte)'T' && bytes[3] == (byte)'X')
            {
                var tempBntx = outPath + ".tmp.bntx";
                File.WriteAllBytes(tempBntx, bytes);
                try
                {
                    using (var bmp = BnTxx.BNTX.LoadFromFile(tempBntx))
                    {
                        if (bmp != null)
                        {
                            bmp.Save(outPath, System.Drawing.Imaging.ImageFormat.Png);
                            Console.WriteLine($"EXTRACTED_PNG {bmp.Width}x{bmp.Height} {outPath}");
                            return;
                        }
                    }
                }
                finally
                {
                    if (File.Exists(tempBntx))
                    {
                        try { File.Delete(tempBntx); } catch { }
                    }
                }
            }

            // Fallback for files that are already PNG or standard image formats
            File.WriteAllBytes(outPath, bytes);
            Console.WriteLine($"EXTRACTED_PNG raw {outPath}");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"ERR Failed to decode/write PNG: {ex.Message}");
        }
    }
}

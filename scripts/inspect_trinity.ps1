$asmCore = [System.Reflection.Assembly]::LoadFrom("D:\Environtment\utilities\trinity\fileexplorer\GFTool.Core.dll")
$asmFE = [System.Reflection.Assembly]::LoadFrom("D:\Environtment\utilities\trinity\fileexplorer\TrinityFileExplorer.dll")

$cachePath = "D:\Environtment\utilities\trinity\fileexplorer\GFPAKHashCache.bin"
$cacheClass = $asmCore.GetType("Trinity.Core.Cache.GFPakHashCache")
Write-Host "Opening cache: $cachePath..."
$openMethod = $cacheClass.GetMethod("Open", [System.Reflection.BindingFlags]"Public,Static")
$openMethod.Invoke($null, @($cachePath))
$countMethod = $cacheClass.GetMethod("get_Count", [System.Reflection.BindingFlags]"Public,Static")
$count = $countMethod.Invoke($null, @())
Write-Host "Cache opened successfully! Total hashes: $count"

$trpfdPath = "E:\Modding\eden\dump\0100A3D008C5C000\romfs\arc\data.trpfd"
$trpfsPath = "E:\Modding\eden\dump\0100A3D008C5C000\romfs\arc\data.trpfs"

$fbc = $asmCore.GetType("Trinity.Core.Utils.FlatBufferConverter")
$cfdType = $asmCore.GetType("Trinity.Core.Flatbuffers.TR.ResourceDictionary.CustomFileDescriptor")
$deserMethod = $fbc.GetMethods() | Where-Object { $_.Name -eq "DeserializeFrom" -and $_.GetParameters()[0].ParameterType -eq [string] }
$deserTyped = $deserMethod[0].MakeGenericMethod($cfdType)

Write-Host "Deserializing TRPFD..."
$cfd = $deserTyped.Invoke($null, @($trpfdPath))
Write-Host "TRPFD loaded! Total files: $($cfd.FileHashes.Length)"

Write-Host "Deserializing FileSystem..."
$oneFileSer = $asmCore.GetType("Trinity.Core.Serializers.TR.ONEFILESerializer")
$fsMethod = $oneFileSer.GetMethod("DeserializeFileSystem", [Type[]]@([string]))
$fs = $fsMethod.Invoke($null, @($trpfsPath))
Write-Host "FileSystem loaded! Total offsets: $($fs.FileOffsets.Length)"

Write-Host "Creating TrpfsExtractor..."
$extType = $asmFE.GetType("TrinityFileExplorer.TrinityExplorerWindow+TrpfsExtractor")
$extractor = [Activator]::CreateInstance($extType, @($cfd, $fs, $trpfsPath))
Write-Host "Extractor created!"

$getNameMethod = $cacheClass.GetMethod("GetName", [System.Reflection.BindingFlags]"Public,Static")

$targetHash = [UInt64]0xa6f0dc7e4e2ea
$targetPath = "message/dat/English/script/field_event.dat"

Write-Host "Found target file: $targetPath (Hash: 0x$($targetHash.ToString('x')))"
$tryGetFileBytes = $extType.GetMethod("TryGetFileBytes", [System.Reflection.BindingFlags]"Public,Instance")
$bytesArg = [byte[]]@()
$params = [object[]]@($targetHash, $bytesArg)
$result = $tryGetFileBytes.Invoke($extractor, $params)

Write-Host "Extraction result: $result"
if ($result) {
    $extractedBytes = $params[1]
    Write-Host "Extracted byte count: $($extractedBytes.Length)"
    Write-Host "Header: $([BitConverter]::ToString($extractedBytes, 0, [Math]::Min(16, $extractedBytes.Length)))"
}


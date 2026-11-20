# SAO Desktop Menu - by Arthur_Zid - Copyright (c) 2026 Arthur_Zid - MIT License (see LICENSE.txt)
# Extracts app icons for the SAO menu.
# Input: a JSON file with [{ "path": "shell:AppsFolder\<AppID>" or a folder path, "out": "<png file>" }, ...]
# Uses the same Windows Shell API that the Start menu uses, so Store apps and normal apps both work.
param([Parameter(Mandatory = $true)][string]$List, [int]$Size = 64)

Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

public static class SaoIcons {
    [ComImport, Guid("bcc18b79-ba16-442f-80c4-8a59c30c463b"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellItemImageFactory { [PreserveSig] int GetImage(SIZE size, int flags, out IntPtr phbm); }

    [StructLayout(LayoutKind.Sequential)]
    struct SIZE { public int cx, cy; public SIZE(int x, int y) { cx = x; cy = y; } }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHCreateItemFromParsingName(string path, IntPtr pbc,
        [MarshalAs(UnmanagedType.LPStruct)] Guid riid,
        [MarshalAs(UnmanagedType.Interface)] out IShellItemImageFactory ppv);

    [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr h);

    public static bool Save(string parsingName, string outPath, int size) {
        IShellItemImageFactory f;
        SHCreateItemFromParsingName(parsingName, IntPtr.Zero, typeof(IShellItemImageFactory).GUID, out f);
        IntPtr hbm;
        int hr = f.GetImage(new SIZE(size, size), 0x4 /* ICONONLY */, out hbm);
        if (hr != 0 || hbm == IntPtr.Zero) return false;
        try {
            using (Bitmap src = Image.FromHbitmap(hbm)) {
                Rectangle r = new Rectangle(0, 0, src.Width, src.Height);
                BitmapData bd = src.LockBits(r, ImageLockMode.ReadOnly, src.PixelFormat);
                try {
                    // keep the alpha channel (FromHbitmap alone drops it)
                    using (Bitmap dst = new Bitmap(bd.Width, bd.Height, bd.Stride, PixelFormat.Format32bppPArgb, bd.Scan0))
                    using (Bitmap copy = new Bitmap(dst)) {
                        copy.Save(outPath, ImageFormat.Png);
                    }
                } finally { src.UnlockBits(bd); }
            }
        } finally { DeleteObject(hbm); }
        return true;
    }
}
'@

$items = Get-Content -Raw -Encoding UTF8 $List | ConvertFrom-Json
$ok = 0; $bad = 0
foreach ($it in $items) {
    try {
        if ([SaoIcons]::Save($it.path, $it.out, $Size)) { $ok++ } else { $bad++ }
    } catch { $bad++ }
}
"icons saved: $ok, failed: $bad"

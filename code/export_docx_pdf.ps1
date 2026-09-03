$ErrorActionPreference = 'Stop'

$docxPath = (Get-ChildItem -LiteralPath 'paper\final' -Filter '*.docx' | Select-Object -First 1).FullName
$pdfPath = [System.IO.Path]::ChangeExtension($docxPath, '.pdf')

$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open($docxPath, $false, $false)
    foreach ($story in $document.StoryRanges) {
        $null = $story.Fields.Update()
    }
    $document.Save()
    $document.ExportAsFixedFormat($pdfPath, 17)
    Write-Output $pdfPath
}
finally {
    if ($null -ne $document) {
        $document.Close($false)
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($document) | Out-Null
    }
    if ($null -ne $word) {
        $word.Quit()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

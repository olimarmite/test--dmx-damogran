# Damogran - version PowerShell (aucune installation, aucun droit admin).
# Meme interface (ui.html) et memes fichiers config.json / state.json que damogran.py.
# Compatible Windows PowerShell 5.1 (inclus dans Windows) et PowerShell 7.
#
#   powershell -ExecutionPolicy Bypass -File damogran.ps1            -> http://localhost:8080
#   powershell -ExecutionPolicy Bypass -File damogran.ps1 -Lan       -> accessible depuis un telephone
#   powershell -ExecutionPolicy Bypass -File damogran.ps1 -Port 9000
param([int]$Port = 8080, [switch]$Lan, [switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $Here 'config.json'
$StatePath = Join-Path $Here 'state.json'
$UiPath = Join-Path $Here 'ui.html'
$Utf8 = New-Object System.Text.UTF8Encoding $false
$ChanTokens = @('R', 'G', 'B', 'W', 'A', 'U')

function Clamp($v, $lo, $hi) { [Math]::Max($lo, [Math]::Min($hi, $v)) }

# ConvertFrom-Json donne des PSCustomObject : on les transforme en hashtables (pas de -AsHashtable en 5.1)
function ConvertTo-Hash($o) {
    if ($null -eq $o) { return $null }
    if ($o -is [System.Management.Automation.PSCustomObject]) {
        $h = @{}
        foreach ($p in $o.PSObject.Properties) { $h[$p.Name] = ConvertTo-Hash $p.Value }
        return $h
    }
    if ($o -is [System.Collections.IList]) {
        $a = New-Object System.Collections.ArrayList
        foreach ($x in $o) { [void]$a.Add((ConvertTo-Hash $x)) }
        return , $a
    }
    return $o
}

function Read-Json($path) {
    try {
        if (-not (Test-Path $path)) { return $null }
        return ConvertTo-Hash ([System.IO.File]::ReadAllText($path) | ConvertFrom-Json)
    } catch { return $null }
}

function Write-Json($path, $data) {
    $tmp = "$path.tmp"
    [System.IO.File]::WriteAllText($tmp, (ConvertTo-Json -InputObject $data -Depth 10), $Utf8)
    Move-Item -Force $tmp $path
}

function Parse-Layout($layout) {
    $out = New-Object System.Collections.ArrayList
    foreach ($tok in ([string]$layout -split '[,; ]+')) {
        $t = $tok.Trim().ToUpper()
        if (-not $t) { continue }
        if ($t -eq '-') { [void]$out.Add([int]0) }
        elseif ($t -match '^\d+$') { [void]$out.Add([int](Clamp ([int]$t) 0 255)) }
        else { [void]$out.Add($t) }
    }
    return , $out
}

function Get-LocalIps {
    try {
        return @([System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
            Where-Object { $_.AddressFamily -eq 'InterNetwork' } | ForEach-Object { $_.ToString() } | Sort-Object -Unique)
    } catch { return @() }
}

# ---- etat --------------------------------------------------------------------
$Config = Read-Json $ConfigPath
if (-not $Config) {
    $fx = New-Object System.Collections.ArrayList
    for ($i = 0; $i -lt 6; $i++) {
        [void]$fx.Add(@{ id = "f$($i + 1)"; name = "Spot $($i + 1)"; universe = 0; address = 1 + $i * 4; layout = 'D,R,G,B' })
    }
    $Config = @{ target_ip = '2.255.255.255'; bind_ip = ''; port = 6454; fps = 30; fixtures = $fx }
}
$State = Read-Json $StatePath
if (-not $State) { $State = @{} }
if (-not $State.ContainsKey('master')) { $State.master = 255 }
if (-not $State.ContainsKey('blackout')) { $State.blackout = $false }
if (-not ($State.fixtures -is [hashtable])) { $State.fixtures = @{} }

$Raw = $null
$Identify = @{}
$LastError = ''
$Packets = 0
$Dirty = $false
$LocalIps = Get-LocalIps
$Udp = $null
$UdpBind = $null

# ---- sortie Art-Net ----------------------------------------------------------
function Get-Udp {
    $bind = [string]$Config.bind_ip
    if ($null -eq $script:Udp -or $script:UdpBind -ne $bind) {
        if ($script:Udp) { $script:Udp.Close() }
        if ($bind) {
            $u = New-Object System.Net.Sockets.UdpClient (New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Parse($bind)), 0)
        } else {
            $u = New-Object System.Net.Sockets.UdpClient
        }
        $u.EnableBroadcast = $true
        $script:Udp = $u
        $script:UdpBind = $bind
    }
    return $script:Udp
}

function Build-Universes {
    $now = Get-Date
    $unis = @{}
    $master = [double]$State.master / 255.0
    foreach ($fx in $Config.fixtures) {
        $uni = [int]$fx.universe
        if (-not $unis.ContainsKey($uni)) { $unis[$uni] = New-Object byte[] 512 }
        $buf = $unis[$uni]
        $st = $State.fixtures[$fx.id]
        if (-not $st) { $st = @{} }
        $layout = Parse-Layout $fx.layout
        $dim = 0.0
        if ($st.ContainsKey('dim')) { $dim = [double]$st.dim / 255.0 * $master }
        if ($State.blackout) { $dim = 0.0 }
        $scale = 1.0
        if (-not $layout.Contains('D')) { $scale = $dim }
        $vals = @{ D = $dim * 255 }
        foreach ($t in $ChanTokens) {
            $k = $t.ToLower()
            $v = 0.0
            if ($st.ContainsKey($k)) { $v = [double]$st[$k] }
            $vals[$t] = $v * $scale
        }
        if ($Identify.ContainsKey($fx.id) -and $Identify[$fx.id] -gt $now) {
            $on = 0
            if (([int][Math]::Floor($now.TimeOfDay.TotalSeconds * 6)) % 2 -eq 0) { $on = 255 }
            $vals = @{ D = $on }
            foreach ($t in $ChanTokens) { $vals[$t] = $on }
        }
        $base = [int]$fx.address - 1
        for ($i = 0; $i -lt $layout.Count; $i++) {
            $ch = $base + $i
            if ($ch -lt 0 -or $ch -ge 512) { continue }
            $tok = $layout[$i]
            if ($tok -is [int]) { $v = $tok }
            elseif ($vals.ContainsKey($tok)) { $v = $vals[$tok] }
            else { $v = 0 }
            $buf[$ch] = [byte](Clamp ([int][Math]::Round([double]$v)) 0 255)
        }
    }
    if ($Raw) {
        $uni = [int]$Raw.universe
        if (-not $unis.ContainsKey($uni)) { $unis[$uni] = New-Object byte[] 512 }
        $ch = [int]$Raw.address - 1
        if ($ch -ge 0 -and $ch -lt 512) { $unis[$uni][$ch] = [byte](Clamp ([int]$Raw.value) 0 255) }
    }
    return $unis
}

$ArtHeader = [byte[]]([System.Text.Encoding]::ASCII.GetBytes("Art-Net") + [byte[]](0, 0x00, 0x50, 0, 14))
$Seq = 0
function Send-Frame {
    $script:Seq = $script:Seq % 255 + 1
    try {
        $udp = Get-Udp
        $ep = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Parse([string]$Config.target_ip)), ([int]$Config.port)
        $unis = Build-Universes
        foreach ($uni in ($unis.Keys | Sort-Object)) {
            $pkt = New-Object byte[] 530
            [Array]::Copy($ArtHeader, $pkt, 12)
            $pkt[12] = [byte]$script:Seq
            $pkt[13] = 0
            $pkt[14] = [byte]($uni -band 0xFF)
            $pkt[15] = [byte](($uni -shr 8) -band 0x7F)
            $pkt[16] = 2       # longueur 512, big-endian
            $pkt[17] = 0
            [Array]::Copy($unis[$uni], 0, $pkt, 18, 512)
            [void]$udp.Send($pkt, 530, $ep)
            $script:Packets++
        }
        $script:LastError = ''
    } catch {
        $script:LastError = "Envoi vers $($Config.target_ip) : $($_.Exception.Message)"
    }
}

# ---- API ---------------------------------------------------------------------
function Get-Snapshot {
    return @{ config = $Config; state = $State; raw = $Raw; error = $LastError; packets = $Packets; local_ips = $LocalIps }
}

function Is-Number($v) { return ($v -is [ValueType]) -and -not ($v -is [bool]) }

function Patch-State($body) {
    if ($body.fixtures -is [hashtable]) {
        foreach ($fid in @($body.fixtures.Keys)) {
            if (-not ($State.fixtures[$fid] -is [hashtable])) { $State.fixtures[$fid] = @{} }
            $cur = $State.fixtures[$fid]
            $vals = $body.fixtures[$fid]
            foreach ($k in @($vals.Keys)) {
                if (Is-Number $vals[$k]) {
                    $max = 255
                    if ($k -eq 'h') { $max = 360 }
                    $cur[$k] = Clamp ([double]$vals[$k]) 0 $max
                }
            }
        }
    }
    if ($body.ContainsKey('master')) { $State.master = [int](Clamp ([double]$body.master) 0 255) }
    if ($body.ContainsKey('blackout')) { $State.blackout = [bool]$body.blackout }
    if ($body.ContainsKey('raw')) { $script:Raw = $body.raw }
    if ($body.identify) {
        foreach ($fid in $body.identify) { $Identify[[string]$fid] = (Get-Date).AddSeconds(2.5) }
    }
    $script:Dirty = $true
}

function Set-Config($cfg) {
    $fixtures = New-Object System.Collections.ArrayList
    $i = 0
    foreach ($fx in $cfg.fixtures) {
        $id = [string]$fx.id
        if (-not $id) { $id = "f$i" + "_" + [DateTime]::Now.Ticks }
        $name = [string]$fx.name
        if (-not $name) { $name = "Spot $($i + 1)" }
        if ($name.Length -gt 40) { $name = $name.Substring(0, 40) }
        $layout = [string]$fx.layout
        if (-not $layout) { $layout = 'D,R,G,B' }
        [void]$fixtures.Add(@{
            id = $id; name = $name; layout = $layout
            universe = [int](Clamp ([int]$fx.universe) 0 32767)
            address = [int](Clamp ([int]$fx.address) 1 512)
        })
        $i++
    }
    $target = ([string]$cfg.target_ip).Trim()
    if (-not $target) { $target = '255.255.255.255' }
    [void][System.Net.IPAddress]::Parse($target)   # refuse une IP invalide
    $bind = ([string]$cfg.bind_ip).Trim()
    if ($bind) { [void][System.Net.IPAddress]::Parse($bind) }
    $port = [int]$cfg.port; if (-not $port) { $port = 6454 }
    $fps = [int]$cfg.fps; if (-not $fps) { $fps = 30 }
    $script:Config = @{ target_ip = $target; bind_ip = $bind; port = $port; fps = (Clamp $fps 1 44); fixtures = $fixtures }
    Write-Json $ConfigPath $script:Config
}

# ---- mini serveur HTTP (TcpListener : pas besoin d'admin, contrairement a HttpListener sur toutes les IP) ----
function Send-Response($client, [int]$code, [byte[]]$body, [string]$ctype) {
    $reason = @{ 200 = 'OK'; 400 = 'Bad Request'; 404 = 'Not Found' }[$code]
    $head = "HTTP/1.1 $code $reason`r`nContent-Type: $ctype`r`nContent-Length: $($body.Length)`r`nCache-Control: no-store`r`nConnection: close`r`n`r`n"
    $hb = [System.Text.Encoding]::ASCII.GetBytes($head)
    $s = $client.GetStream()
    $s.Write($hb, 0, $hb.Length)
    if ($body.Length) { $s.Write($body, 0, $body.Length) }
    $s.Flush()
}

function Send-Json($client, [int]$code, $obj) {
    Send-Response $client $code ($Utf8.GetBytes((ConvertTo-Json -InputObject $obj -Depth 10 -Compress))) 'application/json; charset=utf-8'
}

function Handle-Request($client, [string]$method, [string]$path, [byte[]]$bodyBytes) {
    try {
        if ($method -eq 'GET' -and ($path -eq '/' -or $path -eq '/index.html')) {
            Send-Response $client 200 ([System.IO.File]::ReadAllBytes($UiPath)) 'text/html; charset=utf-8'
        } elseif ($method -eq 'GET' -and $path -eq '/api/state') {
            Send-Json $client 200 (Get-Snapshot)
        } elseif ($method -eq 'POST' -and ($path -eq '/api/state' -or $path -eq '/api/config')) {
            $text = $Utf8.GetString($bodyBytes)
            if (-not $text.Trim()) { $text = '{}' }
            $body = ConvertTo-Hash ($text | ConvertFrom-Json)
            if ($path -eq '/api/state') { Patch-State $body } else { Set-Config $body }
            Send-Json $client 200 @{ ok = $true }
        } else {
            Send-Json $client 404 @{ error = 'not found' }
        }
    } catch {
        try { Send-Json $client 400 @{ error = $_.Exception.Message } } catch { }
    }
}

# Lit sans bloquer : un client n'est traite que quand sa requete est complete,
# pour que l'Art-Net continue a sortir meme si un navigateur ouvre une connexion sans rien envoyer.
function Poll-Client($cl) {
    $c = $cl.client
    while ($c.Available -gt 0) {
        $n = $c.GetStream().Read($cl.tmp, 0, $cl.tmp.Length)
        if ($n -le 0) { break }
        $cl.buf.Write($cl.tmp, 0, $n)
    }
    $bytes = $cl.buf.ToArray()
    $latin = [System.Text.Encoding]::GetEncoding(28591).GetString($bytes)
    $end = $latin.IndexOf("`r`n`r`n")
    if ($end -lt 0) { return $false }
    $lines = $latin.Substring(0, $end) -split "`r`n"
    $parts = $lines[0] -split ' '
    $len = 0
    foreach ($l in $lines) { if ($l -match '^(?i)content-length:\s*(\d+)') { $len = [int]$Matches[1] } }
    if ($bytes.Length -lt $end + 4 + $len) { return $false }
    $body = New-Object byte[] $len
    [Array]::Copy($bytes, $end + 4, $body, 0, $len)
    $path = ($parts[1] -split '\?')[0]
    Handle-Request $c $parts[0] $path $body
    return $true
}

# ---- boucle principale ----------------------------------------------------------
$addr = [System.Net.IPAddress]::Loopback
if ($Lan) { $addr = [System.Net.IPAddress]::Any }
$listener = New-Object System.Net.Sockets.TcpListener $addr, $Port
try {
    $listener.Start()
} catch {
    Write-Host "Impossible d'ouvrir le port $Port : $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Damogran tourne peut-etre deja ? Sinon essaie : -Port 8090"
    exit 1
}
$url = "http://localhost:$Port"
Write-Host "Damogran pret : $url" -ForegroundColor Green
if ($Lan) { foreach ($ip in $LocalIps) { Write-Host "  depuis un telephone : http://${ip}:$Port" } }
Write-Host "Art-Net -> $($Config.target_ip)   (fermer cette fenetre ou Ctrl+C pour quitter)"
if (-not $NoBrowser) { Start-Process $url }

$clients = New-Object System.Collections.ArrayList
$watch = [System.Diagnostics.Stopwatch]::StartNew()
$nextFrame = 0.0
$lastSave = 0.0
try {
    while ($true) {
        while ($listener.Pending()) {
            $c = $listener.AcceptTcpClient()
            [void]$clients.Add(@{ client = $c; buf = (New-Object System.IO.MemoryStream); tmp = (New-Object byte[] 8192); t = $watch.Elapsed.TotalSeconds })
        }
        foreach ($cl in @($clients)) {
            $done = $true
            try { $done = Poll-Client $cl } catch { $done = $true }
            if ($done -or ($watch.Elapsed.TotalSeconds - $cl.t) -gt 10) {
                try { $cl.client.Close() } catch { }
                $clients.Remove($cl)
            }
        }
        $now = $watch.Elapsed.TotalMilliseconds
        if ($now -ge $nextFrame) {
            Send-Frame
            $nextFrame = $now + 1000.0 / (Clamp ([int]$Config.fps) 1 44)
        }
        if ($Dirty -and ($now - $lastSave) -gt 1000) {
            $Dirty = $false
            $lastSave = $now
            try { Write-Json $StatePath $State } catch { }
        }
        Start-Sleep -Milliseconds 5
    }
} finally {
    try { Write-Json $StatePath $State } catch { }
    $listener.Stop()
    if ($Udp) { $Udp.Close() }
}

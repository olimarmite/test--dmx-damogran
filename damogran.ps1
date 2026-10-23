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
$ChanTokens = @('R', 'G', 'B', 'W', 'A', 'U', 'L')
$FadeKeys = @('dim', 'r', 'g', 'b', 'w', 'a', 'u', 'l')   # valeurs fondues lors du rappel d'une memoire
$SceneKeys = $FadeKeys + @('h', 's', 'k')   # k : temperature du blanc choisi (affichage)

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

# ---- couleurs (memes formules que l'interface) -----------------------------------
# Blancs pour projecteurs RGB + lime (ETC ColorSource) : le blanc vient surtout du lime,
# peu de vert et de bleu (l'indigo rosit les peaux). Kelvin, lime, rouge, vert, bleu.
$LimeWhites = @(@(2700, 255, 180, 0, 10), @(3200, 255, 150, 0, 30), @(4000, 255, 125, 15, 55), @(5600, 255, 80, 60, 140), @(6500, 230, 70, 70, 170))

function Get-LimeWhite([double]$k) {
    $t = $LimeWhites
    if ($k -le $t[0][0]) { return @($t[0][1..4]) }
    for ($i = 1; $i -lt $t.Count; $i++) {
        if ($k -le $t[$i][0]) {
            $f = ($k - $t[$i - 1][0]) / ($t[$i][0] - $t[$i - 1][0])
            $out = @()
            for ($j = 1; $j -le 4; $j++) { $out += [int][Math]::Round($t[$i - 1][$j] + ($t[$i][$j] - $t[$i - 1][$j]) * $f) }
            return $out
        }
    }
    return @($t[$t.Count - 1][1..4])
}

# Approximation de Tanner Helland, pour les projecteurs sans lime
function Get-KelvinRgb([double]$k) {
    $t = $k / 100.0
    if ($t -le 66) { $r = 255; $g = 99.4708025861 * [Math]::Log($t) - 161.1195681661 }
    else { $r = 329.698727446 * [Math]::Pow($t - 60, -0.1332047592); $g = 288.1221695283 * [Math]::Pow($t - 60, -0.0755148492) }
    if ($t -ge 66) { $b = 255 } elseif ($t -le 19) { $b = 0 } else { $b = 138.5177312231 * [Math]::Log($t - 10) - 305.0447927307 }
    return @($r, $g, $b | ForEach-Object { [int][Math]::Round((Clamp $_ 0 255)) })
}

function Get-HsRgb([double]$h, [double]$s) {
    $s = $s / 255.0
    $out = @()
    foreach ($n in 5, 3, 1) {
        $k = ($n + $h / 60.0) % 6
        $out += [int][Math]::Round(255 * (1 - $s * [Math]::Max(0, [Math]::Min([Math]::Min($k, 4 - $k), 1))))
    }
    return $out
}

function Get-RgbHs([double]$r, [double]$g, [double]$b) {
    $mx = [Math]::Max($r, [Math]::Max($g, $b))
    $d = $mx - [Math]::Min($r, [Math]::Min($g, $b))
    $h = 0.0
    if ($d) {
        if ($mx -eq $r) { $h = 60 * ((($g - $b) / $d) % 6) }
        elseif ($mx -eq $g) { $h = 60 * (($b - $r) / $d + 2) }
        else { $h = 60 * (($r - $g) / $d + 4) }
    }
    $h = (($h % 360) + 360) % 360
    $s = 0
    if ($mx) { $s = [int][Math]::Round(255 * $d / $mx) }
    return @([int][Math]::Round($h), $s)
}

# Valeurs r,g,b,w,l pour un blanc a k kelvins, selon les canaux du projecteur
function Get-WhiteValues([string]$layout, [double]$k) {
    $toks = Parse-Layout $layout
    $rgb = Get-KelvinRgb $k
    $r = $rgb[0]; $g = $rgb[1]; $b = $rgb[2]
    $hs = Get-RgbHs $r $g $b
    $w = 0; $l = 0
    if ($toks.Contains('L') -and -not $toks.Contains('W')) {
        $lw = Get-LimeWhite $k
        $l = $lw[0]; $r = $lw[1]; $g = $lw[2]; $b = $lw[3]
    } elseif ($toks.Contains('W')) {
        $w = [Math]::Min($r, [Math]::Min($g, $b)); $r -= $w; $g -= $w; $b -= $w
    }
    return @{ r = $r; g = $g; b = $b; w = $w; l = $l; h = $hs[0]; s = $hs[1]; k = [int]([Math]::Round($k / 50.0) * 50) }
}

# Correspondance proposee pour la Mini Connect : faders 1-8 = spots, 9 = blanc, 10 = master
function New-DefaultInput($fixtures) {
    $m = @{}
    $i = 0
    foreach ($fx in $fixtures) {
        if ($i -ge 8) { break }
        $m[[string]($i + 1)] = 'dim:' + $fx.id
        $i++
    }
    $m['9'] = 'white:all'
    $m['10'] = 'master'
    return @{ enabled = $true; universe = 1; map = $m }
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
if (-not ($Config.input -is [hashtable])) { $Config.input = New-DefaultInput $Config.fixtures }
$State = Read-Json $StatePath
if (-not $State) { $State = @{} }
if (-not $State.ContainsKey('master')) { $State.master = 255 }
if (-not $State.ContainsKey('blackout')) { $State.blackout = $false }
if (-not ($State.fixtures -is [hashtable])) { $State.fixtures = @{} }
if (-not ($State.scenes -is [System.Collections.IList])) { $State.scenes = New-Object System.Collections.ArrayList }
if (-not ($State.scenes -is [System.Collections.ArrayList])) { $State.scenes = [System.Collections.ArrayList]@($State.scenes) }
if (-not $State.ContainsKey('fade')) { $State.fade = 2.0 }
if (-not $State.ContainsKey('active_scene')) { $State.active_scene = $null }
$Fade = $null   # fondu en cours : @{ from; to; t0; dur }

$Raw = $null
$Identify = @{}
$LastError = ''
$Packets = 0
$Dirty = $false
$LocalIps = Get-LocalIps
$Udp = $null
$UdpBind = $null
$InValues = New-Object byte[] 512   # derniere valeur recue de la console, par canal
$InSeen = -100.0                    # heure du dernier paquet console
$InSource = ''

# ---- sortie Art-Net ----------------------------------------------------------
function Get-Udp {
    $bind = [string]$Config.bind_ip
    if ($null -eq $script:Udp -or $script:UdpBind -ne $bind) {
        if ($script:Udp) { $script:Udp.Close() }
        $ipa = [System.Net.IPAddress]::Any
        if ($bind) { $ipa = [System.Net.IPAddress]::Parse($bind) }
        # Art-Net : on ecoute sur 6454 pour recevoir les reponses des nodes (ArtPollReply, RDM)
        $u = $null
        foreach ($p in 6454, 0) {
            $u = New-Object System.Net.Sockets.UdpClient
            $u.Client.SetSocketOption([System.Net.Sockets.SocketOptionLevel]::Socket, [System.Net.Sockets.SocketOptionName]::ReuseAddress, $true)
            try { [void]$u.Client.IOControl(-1744830452, [byte[]](0, 0, 0, 0), $null) } catch { }   # Windows : SIO_UDP_CONNRESET off
            try {
                $u.Client.Bind((New-Object System.Net.IPEndPoint $ipa, $p))
                $script:RxOk = ($p -eq 6454)
                break
            } catch {
                $u.Close()
                if ($p -eq 0) { throw }
            }
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

# ---- decouverte : ArtPoll (nodes) + RDM via Art-Net (projecteurs) -------------
# Identifiants de slot RDM (E1.20 table C-2) -> lettre de canal Damogran
$SlotTokens = @{ 0x0001 = 'D'; 0x0002 = 'D'; 0x0205 = 'R'; 0x0206 = 'G'; 0x0207 = 'B'; 0x0211 = 'A'; 0x0212 = 'W'; 0x0213 = 'W'; 0x0214 = 'W' }
$Clock = [System.Diagnostics.Stopwatch]::StartNew()
$RxOk = $false
$Tn = 0
$rnd = New-Object byte[] 4
(New-Object System.Random).NextBytes($rnd)
$SrcUid = [byte[]](@(0x7F, 0xF0) + $rnd)   # plage "prototype" ESTA

function Get-Now { return $Clock.Elapsed.TotalSeconds }

function New-Packet([int]$op) {
    $l = New-Object 'System.Collections.Generic.List[byte]'
    $l.AddRange([System.Text.Encoding]::ASCII.GetBytes("Art-Net"))
    $l.AddRange([byte[]](0, ($op -band 0xFF), ($op -shr 8), 0, 14))
    return , $l
}

function Get-Ascii([byte[]]$d, [int]$off, [int]$len) {
    if ($off -ge $d.Length -or $len -le 0) { return '' }
    $len = [Math]::Min($len, $d.Length - $off)
    $s = [System.Text.Encoding]::ASCII.GetString($d, $off, $len)
    $i = $s.IndexOf([char]0)
    if ($i -ge 0) { $s = $s.Substring(0, $i) }
    return $s.Trim()
}

function Get-U16([byte[]]$d, [int]$i) { return ([int]$d[$i] -shl 8) -bor [int]$d[$i + 1] }

function Get-Hex([byte[]]$d, [int]$off) { return ([BitConverter]::ToString($d, $off, 6) -replace '-', '') }

# Requete RDM GET sans le start code 0xCC (comme l'attend ArtRdm), checksum inclus
function New-RdmGet([byte[]]$dest, [int]$tn, [int]$pidv, [byte[]]$pd) {
    $m = New-Object 'System.Collections.Generic.List[byte]'
    $m.AddRange([byte[]](0xCC, 0x01, (24 + $pd.Length)))
    $m.AddRange($dest)
    $m.AddRange($SrcUid)
    $m.AddRange([byte[]]($tn, 1, 0, 0, 0, 0x20, ($pidv -shr 8), ($pidv -band 0xFF), $pd.Length))
    if ($pd.Length) { $m.AddRange($pd) }
    $sum = 0
    foreach ($b in $m) { $sum += $b }
    $m.RemoveAt(0)
    $m.Add([byte](($sum -shr 8) -band 0xFF))
    $m.Add([byte]($sum -band 0xFF))
    return , $m.ToArray()
}

function Send-To([byte[]]$pkt, [string]$ip) {
    try {
        $ep = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Parse($ip)), ([int]$Config.port)
        [void](Get-Udp).Send($pkt, $pkt.Length, $ep)
    } catch { }   # destination de broadcast injoignable sur ce PC : on ignore
}

function Get-BroadcastTargets {
    $out = New-Object System.Collections.ArrayList
    $list = @([string]$Config.target_ip, '255.255.255.255', '2.255.255.255', '10.255.255.255')
    foreach ($ip in $LocalIps) { if (-not $ip.StartsWith('127.')) { $list += ($ip.Substring(0, $ip.LastIndexOf('.')) + '.255') } }
    foreach ($t in $list) { if ($t -and -not $out.Contains($t)) { [void]$out.Add($t) } }
    return , $out
}

function Get-GuessLayout([int]$fp) {
    if ($fp -le 3) { return ((@('R', 'G', 'B')[0..([Math]::Max($fp, 1) - 1)]) -join ',') }
    return 'D,R,G,B' + (',0' * ($fp - 4))
}

function Reset-Discovery {
    $script:Disc = @{
        running = $false; phase = ''; error = ''; step = ''; next_at = 0.0; flushed = $false
        nodes = @{}; devices = @{}; uids = @{}; slots = @{}; defaults = @{}
        order = (New-Object System.Collections.ArrayList); queue = (New-Object System.Collections.ArrayList); inflight = $null
    }
}
Reset-Discovery

function Start-Discovery {
    Reset-Discovery
    if (-not $script:RxOk) { $script:UdpBind = $null }   # MagicQ a peut-etre ete ferme depuis : on retente le port 6454
    try { [void](Get-Udp) } catch { }
    if (-not $script:RxOk) {
        $Disc.error = "Port Art-Net 6454 occupé : ferme MagicQ (ou tout autre logiciel Art-Net) puis relance."
        return
    }
    $Disc.running = $true
    $Disc.step = 'poll1'
    $Disc.next_at = Get-Now
}

function Receive-PollReply([byte[]]$d, [string]$from) {
    $ip = '{0}.{1}.{2}.{3}' -f $d[10], $d[11], $d[12], $d[13]
    if ($ip -eq '0.0.0.0') { $ip = $from }
    if (-not $Disc.nodes.ContainsKey($ip)) {
        $Disc.nodes[$ip] = @{ ip = $ip; short_name = ''; long_name = ''; universes = (New-Object System.Collections.ArrayList)
            rdm = $false; style = 0; report = ''; mac = '' }
    }
    $n = $Disc.nodes[$ip]
    $n.short_name = Get-Ascii $d 26 18
    $n.long_name = Get-Ascii $d 44 64
    $n.report = Get-Ascii $d 108 64
    if ($d[23] -band 0x02) { $n.rdm = $true }
    if ($d.Length -gt 200) { $n.style = [int]$d[200] }
    if ($d.Length -gt 206) { $n.mac = [BitConverter]::ToString($d, 201, 6) -replace '-', ':' }
    $net = [int]$d[18] -band 0x7F
    $sub = [int]$d[19] -band 0x0F
    for ($i = 0; $i -lt [Math]::Min([int]$d[173], 4); $i++) {
        if ($d[174 + $i] -band 0x80) {   # port de sortie
            $uni = ($net -shl 8) -bor ($sub -shl 4) -bor ([int]$d[190 + $i] -band 0x0F)
            if (-not $n.universes.Contains($uni)) { [void]$n.universes.Add($uni) }
        }
    }
    $n.universes.Sort()
}

function Set-RdmData($dev, [string]$hex, [int]$pidv, [byte[]]$pd) {
    switch ($pidv) {
        0x0060 {
            if ($pd.Length -lt 19) { break }
            $dev.footprint = Get-U16 $pd 10
            $dev.personality = [int]$pd[12]
            $dev.personality_count = [int]$pd[13]
            $dev.address = Get-U16 $pd 14
            $follow = New-Object System.Collections.ArrayList
            foreach ($p in 0x0081, 0x0080, 0x0082) { [void]$follow.Add(@{ uid = $hex; pidv = $p; pd = [byte[]]@(); tries = 0 }) }
            if ($dev.personality) { [void]$follow.Add(@{ uid = $hex; pidv = 0x00E1; pd = [byte[]]@($dev.personality); tries = 0 }) }
            if ($dev.footprint) {
                foreach ($p in 0x0120, 0x0121) { [void]$follow.Add(@{ uid = $hex; pidv = $p; pd = [byte[]]@(); tries = 0 }) }
            }
            $Disc.queue.InsertRange(0, $follow)
        }
        0x0081 { $dev.manufacturer = Get-Ascii $pd 0 $pd.Length }
        0x0080 { $dev.model = Get-Ascii $pd 0 $pd.Length }
        0x0082 { $dev.label = Get-Ascii $pd 0 $pd.Length }
        0x00E1 { if ($pd.Length -ge 3) { $dev.personality_name = Get-Ascii $pd 3 ($pd.Length - 3) } }
        0x0120 {
            $slots = @{}
            for ($i = 0; $i + 5 -le $pd.Length; $i += 5) { $slots[(Get-U16 $pd $i)] = @([int]$pd[$i + 2], (Get-U16 $pd ($i + 3))) }
            $Disc.slots[$hex] = $slots
        }
        0x0121 {
            $defs = @{}
            for ($i = 0; $i + 3 -le $pd.Length; $i += 3) { $defs[(Get-U16 $pd $i)] = [int]$pd[$i + 2] }
            $Disc.defaults[$hex] = $defs
        }
    }
}

function Receive-Rdm([byte[]]$r) {
    if ($r.Length -gt 1 -and $r[0] -eq 0xCC) { $r = [byte[]]$r[1..($r.Length - 1)] }
    if ($r.Length -lt 23 -or $r[0] -ne 0x01 -or $r[19] -ne 0x21) { return }
    $req = $Disc.inflight
    if ($null -eq $req) { return }
    $src = Get-Hex $r 8
    $pidv = Get-U16 $r 20
    if ($src -ne $req.uid -or $pidv -ne $req.pidv -or [int]$r[14] -ne $req.tn) { return }
    $Disc.inflight = $null
    $dev = $Disc.devices[$src]
    if ($null -eq $dev) { return }
    if ($r[15] -ne 0) {   # NACK / ACK_TIMER / OVERFLOW : on fait sans
        if ($pidv -eq 0x0060) { $dev.error = 'Le projecteur refuse la lecture RDM' }
        return
    }
    $pdl = [Math]::Min([int]$r[22], $r.Length - 23)
    $pd = New-Object byte[] $pdl
    if ($pdl -gt 0) { [Array]::Copy($r, 23, $pd, 0, $pdl) }
    Set-RdmData $dev $src $pidv $pd
}

function Receive-ArtNet([byte[]]$d, [string]$from) {
    if ($d.Length -lt 12 -or (Get-Ascii $d 0 8) -ne 'Art-Net') { return }
    $op = [int]$d[8] -bor ([int]$d[9] -shl 8)
    if ($op -eq 0x2100 -and $d.Length -ge 197) {
        Receive-PollReply $d $from
    } elseif ($op -eq 0x8100 -and $d.Length -ge 28) {
        $uni = (([int]$d[21] -band 0x7F) -shl 8) -bor [int]$d[23]
        for ($i = 0; $i -lt [int]$d[27]; $i++) {
            $o = 28 + 6 * $i
            if ($o + 6 -gt $d.Length) { break }
            $hex = Get-Hex $d $o
            if (-not $Disc.devices.ContainsKey($hex)) {
                $u = New-Object byte[] 6
                [Array]::Copy($d, $o, $u, 0, 6)
                $Disc.uids[$hex] = $u
                [void]$Disc.order.Add($hex)
                $Disc.devices[$hex] = @{ uid = ($hex.Substring(0, 4) + ':' + $hex.Substring(4)); ip = $from; universe = $uni
                    manufacturer = ''; model = ''; label = ''; address = 0; footprint = 0; personality = 0; personality_count = 0
                    personality_name = ''; layout = ''; layout_sure = $false; error = '' }
            }
        }
    } elseif ($op -eq 0x8300 -and $d.Length -gt 24) {
        $r = New-Object byte[] ($d.Length - 24)
        [Array]::Copy($d, 24, $r, 0, $r.Length)
        Receive-Rdm $r
    }
}

function Send-ToNodes([int]$op, [int]$cmd) {
    foreach ($n in $Disc.nodes.Values) {
        foreach ($uni in $n.universes) {
            $pkt = New-Packet $op
            $pkt.AddRange((New-Object byte[] 9))
            if ($op -eq 0x8000) { $pkt.AddRange([byte[]]((($uni -shr 8) -band 0x7F), $cmd, 1, ($uni -band 0xFF))) }   # ArtTodRequest
            else { $pkt.AddRange([byte[]]((($uni -shr 8) -band 0x7F), $cmd, ($uni -band 0xFF))) }                     # ArtTodControl
            Send-To $pkt.ToArray() $n.ip
        }
    }
}

function Get-DeviceLayout($dev, [string]$hex) {
    $fp = [int]$dev.footprint
    if (-not $fp) { return @('', $false) }
    $slots = $Disc.slots[$hex]
    if ($null -eq $slots -or $slots.Count -eq 0) { return @((Get-GuessLayout $fp), $false) }
    $defs = $Disc.defaults[$hex]
    if ($null -eq $defs) { $defs = @{} }
    $toks = New-Object System.Collections.ArrayList
    $used = @{}
    for ($off = 0; $off -lt $fp; $off++) {
        $tok = $null
        if ($slots.ContainsKey($off)) {
            $s = $slots[$off]
            if ($s[0] -eq 0 -and $SlotTokens.ContainsKey($s[1])) { $tok = $SlotTokens[$s[1]] }
        }
        if ($tok -and -not $used.ContainsKey($tok)) {
            $used[$tok] = $true
            [void]$toks.Add($tok)
        } else {
            $v = 0
            if ($defs.ContainsKey($off)) { $v = $defs[$off] }
            [void]$toks.Add([string]$v)
        }
    }
    return @(($toks -join ','), ($used.ContainsKey('R') -and $used.ContainsKey('G') -and $used.ContainsKey('B')))
}

function Complete-Discovery([string]$err) {
    foreach ($hex in $Disc.order) {
        $dev = $Disc.devices[$hex]
        $res = Get-DeviceLayout $dev $hex
        $dev.layout = $res[0]
        $dev.layout_sure = [bool]$res[1]
    }
    $Disc.running = $false
    $Disc.error = $err
    $Disc.step = ''
    $Disc.phase = "Terminé : $($Disc.nodes.Count) node(s), $($Disc.devices.Count) projecteur(s) RDM"
    if ($Disc.nodes.Count -and -not $Disc.devices.Count) { $Disc.phase += ' — pas de RDM ici, saisie manuelle nécessaire' }
}

# Appele a chaque tour de boucle : fait avancer la decouverte sans bloquer l'Art-Net ni le serveur web
function Step-Discovery {
    if (-not $Disc.running) { return }
    $now = Get-Now
    $step = $Disc.step
    if (($step -eq 'poll1' -or $step -eq 'poll2') -and $now -ge $Disc.next_at) {
        $Disc.phase = 'Recherche des nodes Art-Net…'
        $pkt = New-Packet 0x2000
        $pkt.AddRange([byte[]](0, 0))
        $bytes = $pkt.ToArray()
        foreach ($ip in (Get-BroadcastTargets)) { Send-To $bytes $ip }
        if ($step -eq 'poll1') { $Disc.step = 'poll2'; $Disc.next_at = $now + 1.0 }
        else { $Disc.step = 'tod'; $Disc.next_at = $now + 2.0 }
    } elseif (($step -eq 'tod' -or $step -eq 'tod2') -and $now -ge $Disc.next_at) {
        if ($Disc.nodes.Count -eq 0) {
            Complete-Discovery "Aucun node Art-Net n'a répondu. Vérifie le câble réseau, la carte choisie et que MagicQ est fermé."
            return
        }
        $Disc.phase = 'Recherche RDM des projecteurs…'
        Send-ToNodes 0x8000 0
        $Disc.step = 'tod_wait'
        $Disc.next_at = $now + 2.5
    } elseif ($step -eq 'tod_wait' -and $now -ge $Disc.next_at) {
        if ($Disc.devices.Count -eq 0 -and -not $Disc.flushed) {
            # Certains nodes ne font la decouverte RDM que sur demande : on la force une fois.
            $Disc.flushed = $true
            $Disc.phase = 'Relance de la découverte RDM sur les nodes…'
            Send-ToNodes 0x8200 1
            $Disc.step = 'tod2'
            $Disc.next_at = $now + 6.0
        } else {
            foreach ($hex in $Disc.order) { [void]$Disc.queue.Add(@{ uid = $hex; pidv = 0x0060; pd = [byte[]]@(); tries = 0 }) }
            $Disc.step = 'rdm'
        }
    } elseif ($step -eq 'rdm') {
        $req = $Disc.inflight
        if ($null -ne $req -and ($now - $req.sent) -gt 0.8) {
            $Disc.inflight = $null
            if ($req.tries -lt 2) { $Disc.queue.Insert(0, $req) }
            elseif ($req.pidv -eq 0x0060) { $Disc.devices[$req.uid].error = 'Pas de réponse RDM' }
        }
        if ($null -eq $Disc.inflight -and $Disc.queue.Count -gt 0) {
            $item = $Disc.queue[0]
            $Disc.queue.RemoveAt(0)
            $item.tries++
            $dev = $Disc.devices[$item.uid]
            $script:Tn = ($script:Tn + 1) % 256
            $uni = [int]$dev.universe
            $pkt = New-Packet 0x8300
            $pkt.AddRange([byte[]](1, 0, 0, 0, 0, 0, 0, 0, 0, (($uni -shr 8) -band 0x7F), 0, ($uni -band 0xFF)))
            $pkt.AddRange((New-RdmGet $Disc.uids[$item.uid] $script:Tn $item.pidv $item.pd))
            Send-To $pkt.ToArray() $dev.ip
            $item.tn = $script:Tn
            $item.sent = $now
            $Disc.inflight = $item
            $done = @($Disc.devices.Values | Where-Object { $_.address -or $_.error }).Count
            $Disc.phase = "Lecture des projecteurs ($done/$($Disc.devices.Count))…"
        } elseif ($null -eq $Disc.inflight) {
            Complete-Discovery ''
        }
    }
}

function Get-DiscoverySnapshot {
    return @{
        running = $Disc.running; phase = $Disc.phase; error = $Disc.error
        nodes = @($Disc.nodes.Values | Sort-Object { $_.ip })
        devices = @($Disc.devices.Values | Sort-Object { $_.universe }, { $_.address })
    }
}

# ---- entree console (Art-Net venant de MagicQ / Mini Connect) --------------------
function Get-OutputUniverses {
    $u = @{}
    foreach ($fx in $Config.fixtures) { $u[[int]$fx.universe] = $true }
    return $u
}

function Receive-Console([byte[]]$d, [string]$from) {
    $inp = $Config.input
    if ($d.Length -lt 18 -or -not ($inp -is [hashtable]) -or -not $inp.enabled) { return }
    $uni = [int]$d[14] -bor (([int]$d[15] -band 0x7F) -shl 8)
    # l'univers de la console doit etre different de ceux des projecteurs (sinon c'est notre propre sortie)
    if ($uni -ne [int]$inp.universe -or (Get-OutputUniverses).ContainsKey($uni)) { return }
    $n = [Math]::Min(512, [Math]::Min((([int]$d[16] -shl 8) -bor [int]$d[17]), $d.Length - 18))
    $now = Get-Now
    # console (re)connectee apres 3 s de silence : on prend les positions sans rien appliquer
    if (($now - $script:InSeen) -le 3.0 -and $inp.map -is [hashtable]) {
        foreach ($chs in @($inp.map.Keys)) {
            $ch = [int]$chs - 1
            if ($ch -ge 0 -and $ch -lt $n -and $d[18 + $ch] -ne $script:InValues[$ch]) {
                Set-ConsoleTarget ([string]$inp.map[$chs]) ([int]$d[18 + $ch]) ([int]$script:InValues[$ch])
            }
        }
    }
    [Array]::Copy($d, 18, $script:InValues, 0, $n)
    $script:InSeen = $now
    $script:InSource = $from
}

function Set-ConsoleTarget([string]$target, [int]$v, [int]$old) {
    $i = $target.IndexOf(':')
    if ($i -ge 0) { $kind = $target.Substring(0, $i); $arg = $target.Substring($i + 1) } else { $kind = $target; $arg = '' }
    $ids = @($Config.fixtures | ForEach-Object { [string]$_.id })
    $targets = @()
    if ($arg -eq 'all') { $targets = $ids } elseif ($ids -contains $arg) { $targets = @($arg) }
    if ($kind -eq 'master') {
        $State.master = $v
    } elseif ($kind -eq 'blackout') {
        if (($v -ge 128) -ne ($old -ge 128)) { $State.blackout = ($v -ge 128) }
    } elseif ($kind -eq 'scene') {
        if ($v -ge 128 -and $old -lt 128) {   # le fader passe la moitie en montant : GO
            foreach ($sc in $State.scenes) {
                if ($sc.id -eq $arg) {
                    $State.active_scene = $sc.id
                    $tg = $sc.fixtures
                    if (-not ($tg -is [hashtable])) { $tg = @{} }
                    Start-Fade $tg ([double]$State.fade)
                }
            }
        }
    } elseif (($kind -eq 'dim' -or $kind -eq 'white' -or $kind -eq 'hue') -and $targets.Count) {
        $script:Fade = $null
        $State.active_scene = $null
        foreach ($fid in $targets) {
            if (-not ($State.fixtures[$fid] -is [hashtable])) { $State.fixtures[$fid] = @{} }
            $cur = $State.fixtures[$fid]
            if ($kind -eq 'dim') {
                $cur.dim = $v
            } elseif ($kind -eq 'white') {
                $fx = $Config.fixtures | Where-Object { $_.id -eq $fid } | Select-Object -First 1
                $wv = Get-WhiteValues ([string]$fx.layout) (2700 + $v * 3800 / 255.0)
                foreach ($k in @($wv.Keys)) { $cur[$k] = $wv[$k] }
            } else {
                $h = [int][Math]::Round($v * 359 / 255.0)
                $s = 255
                if ($cur.ContainsKey('s') -and $cur.s) { $s = [double]$cur.s }
                $rgb = Get-HsRgb $h $s
                $cur.h = $h; $cur.s = $s; $cur.r = $rgb[0]; $cur.g = $rgb[1]; $cur.b = $rgb[2]; $cur.w = 0; $cur.l = 0; $cur.k = 0
            }
        }
    }
    $script:Dirty = $true
}

function Set-Input($body) {
    $inp = $Config.input
    if (-not ($inp -is [hashtable])) { $inp = New-DefaultInput $Config.fixtures }
    if ($body.ContainsKey('enabled')) { $inp.enabled = [bool]$body.enabled }
    if ($body.ContainsKey('universe')) { $inp.universe = [int](Clamp ([int]$body.universe) 0 32767) }
    if ($body.ContainsKey('map')) {
        $m = @{}
        if ($body.map -is [hashtable]) {
            foreach ($k in @($body.map.Keys)) {
                $c = [int]$k
                if ($c -ge 1 -and $c -le 512 -and $body.map[$k]) { $m[[string]$c] = [string]$body.map[$k] }
            }
        }
        $inp.map = $m
    }
    $Config.input = $inp
    Write-Json $ConfigPath $Config
}

# ---- API ---------------------------------------------------------------------
function Get-Snapshot {
    return @{ config = $Config; state = $State; raw = $Raw; error = $LastError; packets = $Packets; local_ips = $LocalIps
        discovery = (Get-DiscoverySnapshot); fading = ($null -ne $script:Fade)
        input = (Get-InputSnapshot) }
}

function Is-Number($v) { return ($v -is [ValueType]) -and -not ($v -is [bool]) }

function Get-InputSnapshot {
    $seen = $null
    if ($script:InSeen -ge 0) { $seen = [Math]::Round((Get-Now) - $script:InSeen, 1) }
    $uni = 1
    if ($Config.input -is [hashtable]) { $uni = [int]$Config.input.universe }
    return @{ values = @($script:InValues[0..23] | ForEach-Object { [int]$_ }); source = $script:InSource; seen = $seen
        conflict = (Get-OutputUniverses).ContainsKey($uni) }
}

function Patch-State($body) {
    if ($body.fixtures -is [hashtable] -and $body.fixtures.Count) {
        # une action manuelle prend la main sur le fondu en cours
        $script:Fade = $null
        $State.active_scene = $null
    }
    if ($body.fixtures -is [hashtable]) {
        foreach ($fid in @($body.fixtures.Keys)) {
            if (-not ($State.fixtures[$fid] -is [hashtable])) { $State.fixtures[$fid] = @{} }
            $cur = $State.fixtures[$fid]
            $vals = $body.fixtures[$fid]
            foreach ($k in @($vals.Keys)) {
                if (Is-Number $vals[$k]) {
                    $max = 255
                    if ($k -eq 'h') { $max = 360 }
                    if ($k -eq 'k') { $max = 20000 }
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

# ---- memoires ------------------------------------------------------------------
function Get-Num($h, [string]$k) {
    if ($h -is [hashtable] -and $h.ContainsKey($k) -and $null -ne $h[$k]) { return [double]$h[$k] }
    return 0.0
}

function Start-Fade($target, [double]$dur) {
    $from = @{}; $to = @{}
    foreach ($fid in @($target.Keys)) {
        if (-not ($State.fixtures[$fid] -is [hashtable])) { $State.fixtures[$fid] = @{} }
        $cur = $State.fixtures[$fid]
        $v = $target[$fid]
        $from[$fid] = @{}; $to[$fid] = @{}
        foreach ($k in $FadeKeys) { $from[$fid][$k] = Get-Num $cur $k; $to[$fid][$k] = Get-Num $v $k }
        $cur.h = Get-Num $v 'h'   # teinte/saturation : uniquement pour l'affichage, pas de fondu
        $cur.s = Get-Num $v 's'
    }
    $script:Fade = @{ from = $from; to = $to; t0 = (Get-Now); dur = $dur }
    Step-Fade
}

function Step-Fade {
    $f = $script:Fade
    if ($null -eq $f) { return }
    $k = 1.0
    if ($f.dur -gt 0) { $k = [Math]::Min(1.0, ((Get-Now) - $f.t0) / $f.dur) }
    foreach ($fid in @($f.to.Keys)) {
        $cur = $State.fixtures[$fid]
        foreach ($key in $FadeKeys) {
            $a = $f.from[$fid][$key]
            $cur[$key] = [Math]::Round($a + ($f.to[$fid][$key] - $a) * $k, 1)
        }
    }
    if ($k -ge 1.0) {
        $script:Fade = $null
        $script:Dirty = $true
    }
}

function Invoke-SceneAction($body) {
    $scenes = $State.scenes
    $sc = $null
    foreach ($x in $scenes) { if ($x.id -eq [string]$body.id) { $sc = $x } }
    $name = ([string]$body.name).Trim()
    if ($name.Length -gt 30) { $name = $name.Substring(0, 30) }
    $act = [string]$body.action
    if ($act -eq 'save') {
        if ($null -eq $sc) {
            if (-not $name) { $name = "Mémoire $($scenes.Count + 1)" }
            $sc = @{ id = "s" + [DateTime]::Now.Ticks; name = $name }
            [void]$scenes.Add($sc)
        } elseif ($name) { $sc.name = $name }
        $snap = @{}
        foreach ($fid in @($State.fixtures.Keys)) {
            $vals = @{}
            foreach ($k in $SceneKeys) { if ($State.fixtures[$fid].ContainsKey($k)) { $vals[$k] = $State.fixtures[$fid][$k] } }
            $snap[$fid] = $vals
        }
        $sc.fixtures = $snap
        $State.active_scene = $sc.id
    } elseif ($act -eq 'rename' -and $sc -and $name) {
        $sc.name = $name
    } elseif ($act -eq 'delete' -and $sc) {
        $scenes.Remove($sc)
        if ($State.active_scene -eq $sc.id) { $State.active_scene = $null }
    } elseif ($act -eq 'recall' -and $sc) {
        $fade = [double]$State.fade
        if ($body.ContainsKey('fade')) { $fade = [double]$body.fade }
        $State.active_scene = $sc.id
        $target = $sc.fixtures
        if (-not ($target -is [hashtable])) { $target = @{} }
        Start-Fade $target (Clamp $fade 0 60)
    } elseif ($act -eq 'fade') {
        $State.fade = [double](Clamp ([double]$body.fade) 0 60)
    } else {
        throw 'Mémoire introuvable ou action inconnue'
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
    $inp = $script:Config.input
    if (-not ($inp -is [hashtable])) { $inp = New-DefaultInput $fixtures }
    $script:Config = @{ target_ip = $target; bind_ip = $bind; port = $port; fps = (Clamp $fps 1 44); fixtures = $fixtures; input = $inp }
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
        } elseif ($method -eq 'POST' -and $path -eq '/api/input') {
            Set-Input (ConvertTo-Hash ($Utf8.GetString($bodyBytes) | ConvertFrom-Json))
            Send-Json $client 200 @{ ok = $true }
        } elseif ($method -eq 'POST' -and $path -eq '/api/scene') {
            $text = $Utf8.GetString($bodyBytes)
            Invoke-SceneAction (ConvertTo-Hash ($text | ConvertFrom-Json))
            Send-Json $client 200 @{ ok = $true }
        } elseif ($method -eq 'POST' -and $path -eq '/api/discover') {
            Start-Discovery
            Send-Json $client 200 @{ ok = $true }
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
        if ($Udp) {
            while ($Udp.Available -gt 0) {
                $remote = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Any), 0
                try { $data = $Udp.Receive([ref]$remote) } catch { break }
                if ($data.Length -le 9) { continue }
                if ($data[8] -eq 0 -and $data[9] -eq 0x50) {   # ArtDmx : peut-etre la console
                    try { Receive-Console $data $remote.Address.ToString() } catch { }
                } else {
                    try { Receive-ArtNet $data $remote.Address.ToString() } catch { }
                }
            }
        }
        try { Step-Discovery } catch { Complete-Discovery "Erreur pendant la découverte : $($_.Exception.Message)" }
        $now = $watch.Elapsed.TotalMilliseconds
        if ($now -ge $nextFrame) {
            Step-Fade
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

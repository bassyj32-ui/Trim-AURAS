# TrimAURA diag suite — synthesize a real speech track via Windows TTS.
# Output: tmp/diag/speech.wav (~2.5-3 min of spoken English, ~1x realtime to
# generate). The video generator then loops/trims this track with ffmpeg so
# every "speech" matrix video exercises the Groq transcription path for real.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$outDir = Join-Path (Split-Path $PSScriptRoot -Parent) "tmp\diag"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$out = Join-Path $outDir "speech.wav"

$paragraph = @"
Welcome to today's lesson on turning long videos into viral shorts. The most important thing to understand is that attention is the currency of social media. When someone scrolls past your content, you have less than two seconds to convince them to stop and watch. That is why the first frame matters so much. A strong opening hook should ask a question, tease a payoff, or start in the middle of the action. Avoid long introductions and slow build ups entirely.

The second principle is momentum. Every single second of your short should either advance the story or raise the stakes. If a moment does not serve the narrative, cut it out without mercy. Viewers can feel dead air instantly, and they will swipe away the moment the video slows down. Pacing is not about being fast, it is about being intentional.

Third, think about the vertical format. Your short is nine by sixteen, which means you must compose every frame for a phone held upright. Keep the subject centered, keep text large enough to read at arm's length, and remember that captions are not optional. A huge percentage of viewers watch with the sound off, especially in public places and on their commute. Good captions turn a silent video into a story.

Now let us talk about the editing workflow itself. Start by transcribing the full video and looking for the best thirty seconds. A great clip has a clear beginning, a satisfying middle, and a payoff at the end. It should work on its own, even if someone never sees the rest of the video. Ask yourself what single idea you want the viewer to remember, and build the clip around that idea alone.

Finally, measure everything and iterate. Post your shorts at the same time each day, study the retention graph, and note exactly where viewers drop off. Then adjust your hooks and your pacing accordingly. Consistency beats perfection, and shipping every day teaches you more than polishing one video for a week. Remember, the goal is not to make content. The goal is to build a habit of making content that earns attention, one short clip at a time.
"@

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $synth.Rate = 0
    $synth.SetOutputToWaveFile($out)
    $synth.Speak($paragraph)
} finally {
    $synth.Dispose()
}

$len = (New-Object System.IO.FileInfo($out)).Length
Write-Host "speech.wav generated: $([math]::Round($len/1MB,1)) MB"

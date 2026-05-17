# Copy this file to config.local.ps1 and edit local tool paths.
# config.local.ps1 is ignored by Git because it may contain private machine paths.

# Required for transcription. Point this to your local video2md.ps1.
$env:VIDEO2MD_SCRIPT = "D:\path\to\video2md\video2md.ps1"

# Optional if video2md can find yt-dlp by itself.
$env:YTDLP_PATH = "D:\path\to\yt-dlp.exe"

# Required by most video2md setups.
$env:FFMPEG_PATH = "D:\path\to\ffmpeg.exe"

# Option A: call a faster-whisper executable directly through video2md.
# $env:WHISPER_EXE_PATH = "D:\path\to\faster-whisper-xxl.exe"

# Option B: use scripts\whisper_cpp_cublas_adapter.ps1.
# Keep WHISPER_EXE_PATH unset, then configure these two directories.
$env:WHISPER_CPP_ROOT = "D:\path\to\Whisper\Cpp"
$env:WHISPER_CPP_CUBLAS_ROOT = "D:\path\to\Whisper\CppCuBlas"

# Optional: use conda instead of .venv.
# $env:CONDA_EXE = "D:\path\to\conda.exe"

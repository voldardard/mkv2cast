# mkv2cast bash completion script
# Copyright (C) 2024-2026 voldardard
# License: GPL-3.0
#
# Installation:
#   Copy to ~/.local/share/bash-completion/completions/mkv2cast
#   Or source this file in your ~/.bashrc

_mkv2cast_completions() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    
    # All available options
    opts="
        -h --help
        -V --version
        -r --recursive --no-recursive
        -d --debug
        -n --dryrun
        -I --ignore-pattern
        -i --include-pattern
        --ignore-path
        --include-path
        --suffix
        --container
        --skip-when-ok --no-skip-when-ok
        --force-h264
        --allow-hevc
        --force-aac
        --keep-surround
        --no-silence
        --abr
        --crf
        --preset
        --hw
        --vaapi-device
        --vaapi-qp
        --qsv-quality
        --integrity-check --no-integrity-check
        --stable-wait
        --deep-check
        --no-progress
        --bar-width
        --ui-refresh-ms
        --stats-period
        --pipeline --no-pipeline
        --encode-workers
        --integrity-workers
        --notify --no-notify
        --lang
        --show-dirs
        --history
        --history-stats
        --clean-tmp
        --clean-logs
        --clean-history
        --check-requirements
    "
    
    # Handle options that require specific values
    case "${prev}" in
        --container)
            COMPREPLY=( $(compgen -W "mkv mp4" -- "${cur}") )
            return 0
            ;;
        --hw)
            COMPREPLY=( $(compgen -W "auto vaapi qsv cpu" -- "${cur}") )
            return 0
            ;;
        --preset)
            COMPREPLY=( $(compgen -W "ultrafast superfast veryfast faster fast medium slow slower veryslow" -- "${cur}") )
            return 0
            ;;
        --vaapi-device)
            # Complete device paths
            COMPREPLY=( $(compgen -f -- "${cur}") )
            return 0
            ;;
        --suffix)
            # Common suffixes
            COMPREPLY=( $(compgen -W ".cast .converted .chromecast" -- "${cur}") )
            return 0
            ;;
        --abr)
            # Common audio bitrates
            COMPREPLY=( $(compgen -W "128k 160k 192k 256k 320k" -- "${cur}") )
            return 0
            ;;
        --crf)
            # CRF values
            COMPREPLY=( $(compgen -W "18 19 20 21 22 23 24 25 26 28" -- "${cur}") )
            return 0
            ;;
        --vaapi-qp|--qsv-quality)
            # QP/Quality values
            COMPREPLY=( $(compgen -W "18 19 20 21 22 23 24 25 26 28" -- "${cur}") )
            return 0
            ;;
        --stable-wait)
            # Wait seconds
            COMPREPLY=( $(compgen -W "1 2 3 4 5 10" -- "${cur}") )
            return 0
            ;;
        --encode-workers|--integrity-workers)
            # Worker counts
            COMPREPLY=( $(compgen -W "0 1 2 3 4 5 6" -- "${cur}") )
            return 0
            ;;
        --bar-width)
            COMPREPLY=( $(compgen -W "20 25 26 30 40 50" -- "${cur}") )
            return 0
            ;;
        --ui-refresh-ms)
            COMPREPLY=( $(compgen -W "50 100 120 150 200 250" -- "${cur}") )
            return 0
            ;;
        --stats-period)
            COMPREPLY=( $(compgen -W "0.1 0.2 0.5 1.0" -- "${cur}") )
            return 0
            ;;
        --clean-logs|--clean-history)
            # Days
            COMPREPLY=( $(compgen -W "7 14 30 60 90" -- "${cur}") )
            return 0
            ;;
        --history)
            # Number of lines
            COMPREPLY=( $(compgen -W "10 20 50 100 200 500 1000" -- "${cur}") )
            return 0
            ;;
        --lang)
            # Supported languages
            COMPREPLY=( $(compgen -W "en fr es it de" -- "${cur}") )
            return 0
            ;;
        -I|--ignore-pattern|-i|--include-pattern)
            # Pattern examples (user typically types their own)
            COMPREPLY=( $(compgen -W "'*sample*' '*.eng.*' '*2024*' '*.French.*'" -- "${cur}") )
            return 0
            ;;
        --ignore-path|--include-path)
            # Complete directories
            COMPREPLY=( $(compgen -d -- "${cur}") )
            return 0
            ;;
    esac
    
    # Complete options if current word starts with -
    if [[ "${cur}" == -* ]]; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi
    
    # Complete MKV files and directories
    # Use compgen -f for files, filter to .mkv and directories
    local IFS=$'\n'
    COMPREPLY=( $(compgen -f -- "${cur}") )
    
    # Filter to only show .mkv files and directories
    local filtered=()
    for f in "${COMPREPLY[@]}"; do
        if [[ -d "$f" ]]; then
            filtered+=("$f/")
        elif [[ "$f" == *.mkv || "$f" == *.MKV ]]; then
            filtered+=("$f")
        fi
    done
    COMPREPLY=("${filtered[@]}")
    
    return 0
}

# Register completion function
complete -F _mkv2cast_completions mkv2cast

\
    @echo off
    setlocal enabledelayedexpansion
    cd /d %~dp0

    echo OPZ_FREEZE_F3_T1: START
    py tools\opz_step_ctl.py --freeze F3-T1 --reason "IBKR onboarding pending" --advance-to F6-T1 || exit /b 2

    echo OPZ_FREEZE_F3_T1: reconcile + manifest + certify
    py tools\reconcile_step_index.py || exit /b 2
    py tools\rebuild_manifest.py || exit /b 2
    py tools\verify_manifest.py || exit /b 2
    py tools\certify_steps.py || exit /b 2
    py tools\release_status.py --format md

    echo OPZ_FREEZE_F3_T1: DONE
    exit /b 0

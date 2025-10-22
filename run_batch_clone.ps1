#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Batch CO Series Cloning Script for PowerShell

.DESCRIPTION
    This script provides an interactive interface for running the batch CO series cloner
    with various configuration options.

.PARAMETER AutoStart
    Automatically start cloning from CO 31 without prompting

.PARAMETER StartSeries
    Specify the starting series number

.PARAMETER EndSeries
    Specify the ending series number

.PARAMETER BatchSize
    Specify the batch size (default: 10)

.PARAMETER Delay
    Specify the delay between series in seconds (default: 3)

.EXAMPLE
    .\run_batch_clone.ps1
    .\run_batch_clone.ps1 -AutoStart
    .\run_batch_clone.ps1 -StartSeries 31 -EndSeries 50
#>

param(
    [switch]$AutoStart,
    [int]$StartSeries = 31,
    [int]$EndSeries = 0,
    [int]$BatchSize = 10,
    [int]$Delay = 3
)

function Show-Banner {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "    Batch CO Series Cloning Script" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
}

function Show-Menu {
    Write-Host "Choose an option:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "1. Continue from where we left off (CO 31+)" -ForegroundColor Green
    Write-Host "2. Clone specific range (e.g., CO 31-50)" -ForegroundColor Green
    Write-Host "3. Clone all remaining CO series" -ForegroundColor Green
    Write-Host "4. Custom configuration" -ForegroundColor Green
    Write-Host "5. Show current progress" -ForegroundColor Green
    Write-Host "6. Exit" -ForegroundColor Red
    Write-Host ""
}

function Get-UserChoice {
    do {
        $choice = Read-Host "Enter your choice (1-6)"
        if ($choice -match '^[1-6]$') {
            return [int]$choice
        }
        Write-Host "Invalid choice! Please enter 1-6." -ForegroundColor Red
    } while ($true)
}

function Start-Cloning {
    param(
        [string]$Arguments
    )
    
    Write-Host ""
    Write-Host "Starting batch cloning with arguments: $Arguments" -ForegroundColor Green
    Write-Host "Press Ctrl+C to stop at any time" -ForegroundColor Yellow
    Write-Host ""
    
    try {
        & python batch_clone_co_series.py $Arguments.Split(' ')
    }
    catch {
        Write-Host "Error running batch cloner: $_" -ForegroundColor Red
    }
}

function Show-Progress {
    Write-Host ""
    Write-Host "Checking current progress..." -ForegroundColor Yellow
    
    try {
        & python main.py stats
    }
    catch {
        Write-Host "Error getting stats: $_" -ForegroundColor Red
    }
}

# Main execution
if ($AutoStart) {
    Show-Banner
    $args = "--start-series $StartSeries"
    if ($EndSeries -gt 0) {
        $args += " --end-series $EndSeries"
    }
    $args += " --batch-size $BatchSize --delay $Delay"
    
    Start-Cloning -Arguments $args
    exit
}

# Interactive mode
do {
    Show-Banner
    Show-Menu
    
    $choice = Get-UserChoice
    
    switch ($choice) {
        1 {
            Write-Host ""
            Write-Host "Starting from CO 31 (continuing from where we left off)..." -ForegroundColor Green
            Start-Cloning -Arguments "--start-series 31 --batch-size 10 --delay 3"
        }
        2 {
            Write-Host ""
            $start = Read-Host "Enter start series number"
            $end = Read-Host "Enter end series number"
            
            if ($start -match '^\d+$' -and $end -match '^\d+' -and [int]$start -le [int]$end) {
                Write-Host "Cloning CO $start-$end..." -ForegroundColor Green
                Start-Cloning -Arguments "--start-series $start --end-series $end --batch-size 10 --delay 3"
            } else {
                Write-Host "Invalid range! Start must be <= End and both must be numbers." -ForegroundColor Red
                Read-Host "Press Enter to continue"
            }
        }
        3 {
            Write-Host ""
            Write-Host "Cloning all remaining CO series..." -ForegroundColor Green
            Start-Cloning -Arguments "--start-series 31 --batch-size 10 --delay 3"
        }
        4 {
            Write-Host ""
            Write-Host "Running with custom configuration..." -ForegroundColor Green
            Start-Cloning -Arguments ""
        }
        5 {
            Show-Progress
            Read-Host "Press Enter to continue"
        }
        6 {
            Write-Host "Goodbye!" -ForegroundColor Green
            exit 0
        }
    }
    
    if ($choice -ne 5) {
        Write-Host ""
        Write-Host "Batch cloning completed!" -ForegroundColor Green
        Read-Host "Press Enter to return to menu"
    }
    
} while ($true)

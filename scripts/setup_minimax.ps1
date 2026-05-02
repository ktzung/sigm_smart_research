<#
Small helper script that prints out one-command steps to configure MiniMax tooling locally.
This script does not perform remote installs or store secrets in the repo.
#>

Write-Host "MiniMax local setup helper"
Write-Host "1) Set your API key in the current session (recommended):"
Write-Host "   $env:MINIMAX_API_KEY = 'YOUR_API_KEY'"
Write-Host "2) (Optional) Login to the MiniMax CLI (mmx):"
Write-Host "   mmx auth login --api-key $env:MINIMAX_API_KEY"
Write-Host "3) Check quota using the CLI:"
Write-Host "   mmx quota"
Write-Host "4) Generate an image quickly via CLI:"
Write-Host "   mmx image generate --prompt 'A research lab sketch' --size 1024"
Write-Host "5) If you use MCP/Claude Code, follow the README examples in the repo to register coding plans locally."

Write-Host "Notes: This script only prints instructions to avoid writing secrets into the project files."

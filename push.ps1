param(
    [string]$Message = "Aggiornamento automatico"
)

git add .
git commit -m $Message
git push origin main

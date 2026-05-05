0. jeśli od zera, to zrób git clone.
1. zrób zmiany w katalogu git
2. git add .
3. git commit -m 'opis zmiany'
4. git push -u origin main
--- po stronie truenas:
6. docker compose down
7. git fetch origin
8. git reset --hard origin/main
9. docker build -t backgroundremover-api:latest .
10 APPS -> restart
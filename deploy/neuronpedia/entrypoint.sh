#!/bin/sh
# Migrates the database, seeds it when it has no users yet, then serves the webapp on :3000.
set -eu
npx prisma migrate deploy
if node -e "new (require('@prisma/client').PrismaClient)().user.count().then(n => process.exit(n ? 1 : 0))"; then
    npx prisma db seed
fi
exec npx next start -p 3000

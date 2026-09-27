# Neuronpedia's webapp at a pinned commit, for loupe's embedded feature pages (just neuronpedia).
FROM node:22-slim
ARG REF=5a880652d1c5dfaaeeded718287aaca6976b4770
ADD https://github.com/hijohnnylin/neuronpedia.git#${REF}:apps/webapp /np/apps/webapp
WORKDIR /np/apps/webapp
# admin routes (feature imports) are open when the site is local; upstream only counts :3000 as local
RUN grep -q "NEXT_PUBLIC_URL === 'http://localhost:3000'" lib/env.ts && sed -i \
    "s|NEXT_PUBLIC_URL === 'http://localhost:3000'|NEXT_PUBLIC_URL?.startsWith('http://localhost:') === true|" \
    lib/env.ts
RUN npm ci --no-audit --no-fund
ARG PORT=3100
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_URL=http://localhost:${PORT} \
    NEXTAUTH_URL=http://localhost:${PORT} \
    NEURONPEDIA_ENVIRONMENT=dev \
    NEXT_PUBLIC_ENABLE_SIGNIN=false \
    NEXT_PUBLIC_DEMO_MODE=false \
    NEXT_PUBLIC_DEFAULT_MODELID=gemma-2-2b \
    NEXT_PUBLIC_DEFAULT_SOURCESET=gemmascope-res-16k \
    NEXT_PUBLIC_DEFAULT_SOURCE=20-gemmascope-res-16k \
    NEXT_PUBLIC_DEFAULT_RELEASE_NAME=gemma-scope \
    NEXT_PUBLIC_DEFAULT_STEER_MODEL=gemma-2-2b-it \
    NEXT_PUBLIC_STEER_FORCE_ALLOW_INSTRUCT_MODELS=gemma-2-2b-it
RUN npx prisma generate && npx next build
COPY entrypoint.sh /entrypoint.sh
EXPOSE 3000
ENTRYPOINT ["/entrypoint.sh"]

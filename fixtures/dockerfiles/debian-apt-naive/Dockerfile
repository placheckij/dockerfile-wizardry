# Bad on purpose: an apt install that keeps recommended packages and the package lists,
# and a container that runs as root. Linted only, never built.
FROM debian:trixie-slim

RUN apt-get update && apt-get install -y curl ca-certificates

USER root
ENTRYPOINT ["curl"]
CMD ["--version"]

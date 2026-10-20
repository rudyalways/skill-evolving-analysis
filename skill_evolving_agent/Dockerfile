FROM python:3.12-slim

WORKDIR /opt/skill-evolver

COPY skill_evolving_agent/evolver_skills skill_evolving_agent/evolver_skills
COPY skill_evolving_agent/readme.md skill_evolving_agent/run-guide.md skill_evolving_agent/
COPY skill_evolving_agent/workspace skill_evolving_agent/workspace
COPY skill_evolving_agent/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY data/skill_capabilites data/skill_capabilites

RUN chmod +x /usr/local/bin/docker-entrypoint.sh

WORKDIR /opt/skill-evolver/skill_evolving_agent

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sleep", "infinity"]

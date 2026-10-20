# A scheduled, unattended Feedback Brief run (see setup/SKILL.md, Schedule).
# It carries only the run skill: setup/ is removed, so the agent has no instructions for changing its own reach.
# Gemini CLI signs in to Vertex AI as the Cloud Run job's service account; secrets arrive as environment variables.
# Tools are auto-approved (--yolo) because nobody is there to approve them: the boundary is this container, the job's
# least privilege service account, and the send gate, which runs after the agent finishes, not inside it.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm git && rm -rf /var/lib/apt/lists/* \
    && npm install -g @google/gemini-cli
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN rm -rf setup .env runs && mkdir runs && chmod -R a-w /app && chmod -R u+w /app/runs
ENV GOOGLE_GENAI_USE_VERTEXAI=true
# PROFILE, GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION are set on the Cloud Run job; a Cloud Storage bucket is
# mounted at /app/runs so runs persist. The .git folder is kept so the send gate can verify the engine is unchanged.
CMD gemini --yolo -p "Run the feedback brief for profile ${PROFILE}, following SKILL.md. This is a scheduled run: stop after step 3; the job sends it." \
    && python3 engine/steps/send.py "${PROFILE}"

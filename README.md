# Line Scanner | Real-Time +EV Betting Engine

Line Scanner is a full-stack data processing engine designed to identify Positive Expected Value (+EV) opportunities in sports betting markets. 

By continuously polling sharp sportsbooks (e.g., Pinnacle) and applying the multiplicative method to remove the vigorish, the engine derives the "true" implied probability of an event. It then compares these true odds against retail sportsbooks (e.g., FanDuel) in real-time, pushing mathematically profitable discrepancies to a React dashboard via WebSockets before the lines adjust.

## Tech Stack
* **Backend:** Python, FastAPI, Celery, Redis
* **Database:** PostgreSQL, SQLAlchemy
* **Frontend:** Next.js, React, WebSockets
* **Infrastructure:** Docker, Docker Compose

## Quick Start
To spin up the entire microservice architecture locally:

```bash
git clone [https://github.com/daniellin135/line-scanner.git](https://github.com/daniellin135/line-scanner.git)
cd line-scanner
docker compose up --build
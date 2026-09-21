# Projects

**Project**: [KSU24](https://ksu24.kspu.edu/) — Zoom integration & attendance automation

**Description**: Digital e-university platform of Kherson State University (academic journals, chats, and other learning-process tooling). Built the module integrating the platform with Zoom for meeting management and automatic student attendance marking based on Zoom meeting data.

**Responsibilities**: Designed and implemented the Zoom integration module using Hexagonal (Ports & Adapters) architecture — a custom Zoom REST API v2 client (Server-to-Server OAuth) and a domain attendance-analysis service that merges Zoom participant session data into student attendance records, exposed via a django-ninja API. Applies the same architectural discipline (domain isolation, ports/adapters boundaries) used in the .NET microservices work at Onseo and Whimsy Games, just in a Python/Django stack.

**Contribution**: Automated attendance tracking, significantly cutting the time teachers spend on routine attendance processes and giving them clean, ready-to-use statistics.

**Technologies**: Python 3.13, Django 5.2.9, django-ninja, DRF, Pydantic, httpx, Celery, PostgreSQL, Redis, RabbitMQ, Docker

---

**Project**: [How Many Slices?](https://coda.io/@are-you-fruits/how-many-slices/tutorial-21) — "Are you fruits?" indie game studio

**Description**: 2D (grid tile-map) top-down coop game about cooking.

**Responsibilities**: Project/Team Management, DevOps, CI|CD pipeline configuration, Narrative Design.

**Technologies**: Rust, [FruitsEngine](https://github.com/are-you-fruits-studio/fruits_engine), .NET, SCRUM :)

---

**Project**: [True Story Time](https://store.steampowered.com/app/2836730/True_Story_Time/?l=ukrainian) — "Are you fruits?" indie game studio, on Steam

**Description**: Party text video game where you create a "real" story with your friends.

**Responsibilities**: Write backend in .Net 8, deployment on own Raspberry Pi 4 linux server.

**Technologies**: .NET 8, ASP.NET, Redis, Unity

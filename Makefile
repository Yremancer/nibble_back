ifeq ($(OS),Windows_NT)
	SLEEP := timeout /t 10 /nobreak

else
	SLEEP := sleep 4
endif

COMPOSE := docker compose -f docker-compose.yaml

merge:
	git checkout main
	git pull
	git merge dev
	git push
	git checkout dev

# dev

start:
	$(COMPOSE) up --build -d backend db
	$(SLEEP)
	$(COMPOSE) exec backend python -m alembic upgrade head

rebuild:
	$(COMPOSE) down -v
	$(COMPOSE) up --build -d backend db
	$(SLEEP)
	$(COMPOSE) exec backend python -m alembic upgrade head

down:
	$(COMPOSE) down

update-api:
	$(COMPOSE) restart backend

update-db:
	$(COMPOSE) exec backend python -m alembic upgrade head

new-migr:
	$(COMPOSE) exec backend python -m alembic revision --autogenerate -m "$(name)"

see-db:
	$(COMPOSE) exec db sh -c 'exec psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

see-api:
	$(COMPOSE) logs -f backend $(if $(time),--since "$(time)")

dump:
	$(COMPOSE) exec -T db sh -c 'exec pg_dump -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" --file="/dumps/$$(date +%Y-%m-%d_%H-%M-%S).sql"'


# AI skills: источник — .agents/skills, Claude Code читает .claude/skills (копия, в git не идёт)
skills:
	rm -rf .claude/skills
	mkdir -p .claude
	cp -R .agents/skills .claude/skills

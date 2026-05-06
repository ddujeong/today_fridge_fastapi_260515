psql -h localhost -U postgres -d today_fridge

uvicorn app.main:app --reload 
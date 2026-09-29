#python -m crawl.db
sleep 10
python -m crawl.govtrack &>> /app/logs/log.txt &
echo "Starting Streamlit"
python -m src.crawl &>> /app/logs/crawl.txt 
streamlit run app.py --server.port 8501 --server.address=0.0.0.0 &>> /app/logs/streamlit.txt
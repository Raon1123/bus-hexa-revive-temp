import psycopg2
import yaml
import os

from typing import Union

class BUS_TIMELOG():
    def __init__(self):
        # Try container path first, then fallback to local development path
        secret_paths = ["/app/secret/db.yaml", "secret/db.yaml"]
        secret = None
        for candidate in secret_paths:
            try:
                secret = self._get_secret(candidate)
                break
            except FileNotFoundError:
                continue
        if secret is None:
            raise FileNotFoundError("Database secret file not found at /app/secret/db.yaml or secret/db.yaml")


        if 'DB_HOST' in os.environ:
             self.db = psycopg2.connect(
                host=os.environ['DB_HOST'],
                port=os.environ['DB_PORT'],
                dbname=os.environ['DB_NAME'],
                user=os.environ['DB_USER'],
                password=os.environ['DB_PASSWORD']
            )
        else:
            self.db = psycopg2.connect(
                host=secret['host'],
                port=secret['port'],
                dbname=secret['dbname'],
                user=secret['user'],
                password=secret['password']
            )
        self.curser = self.db.cursor()
        
        # initialize table
        query = """
            CREATE TABLE IF NOT EXISTS bus_timelog
            (
                idx VARCHAR(40),
                stop_id VARCHAR(20),
                route_id VARCHAR(20),
                route_nm VARCHAR(20),
                vehicle_number VARCHAR(20),
                stop_name VARCHAR(50)
            )
        """
        try:
            self.curser.execute(query)
            self.db.commit()
        except:
            raise Exception("Failed to initialize table")
        
    def __del__(self):
        self.db.close()
        self.curser.close()
    
    def _get_secret(self,
                    path: str):
        # read yaml 
        with open(path, 'r') as f:
            secret = yaml.safe_load(f)
        return secret
    
    def _execute(self,
                 query: str,
                 args: tuple=()):
        self.curser.execute(query, args)
    
    def _fetchall(self):
        return self.curser.fetchall()
    
    def _commit(self):
        self.db.commit()
        
    def insert_log(self,
                   inputs: tuple):
        query = """
            INSERT INTO bus_timelog
            (idx, stop_id, route_id, vehicle_number)
            VALUES (%s, %s, %s, %s)
        """
        self._execute(query, inputs)
        self._commit()
        
    def add_day_query(self,
                      query: str,
                      args: tuple,
                      targetday: str):
        append_query = """
            AND idx LIKE %s
        """
        args = args + (targetday + "_%%",)
        query += append_query
        return query, args
        
        
    def get_log_by_route_id(self,
                            route_id: str,
                            targetday: Union[str, None]=None):
        # match index format %Y%m%d_%H:%M:%S
        # match only date
        query = """
            SELECT * FROM bus_timelog
            WHERE route_id = %s
        """
        args = (route_id,)
        if targetday is not None:
            query, args = self.add_day_query(query, args, targetday)
    
        self._execute(query, args)
        return self._fetchall()
    
    def get_by_stop_id(self,
                       stop_id: str,
                       targetday: Union[str, None]=None):
          query = """
                SELECT * FROM bus_timelog
                WHERE stop_id = %s
          """
          self._execute(query, (stop_id,))
          return self._fetchall()
      
    def get_by_vehicle_number(self,
                                vehicle_number: str,
                                targetday: Union[str, None]=None):
            query = """
                SELECT * FROM bus_timelog
                WHERE vehicle_number = %s
            """
            self._execute(query, (vehicle_number,))
            return self._fetchall()
    
    def get_all(self):
        query = """
            SELECT * FROM bus_timelog
        """
        self._execute(query)
        return self._fetchall()
    
    def clear_table(self):
        query = """
            DELETE FROM bus_timelog
        """
        self._execute(query)
        self._commit()
        
        
if __name__ == '__main__':
    db = BUS_TIMELOG()
    db.clear_table()

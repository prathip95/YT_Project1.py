import streamlit as st
import json
import pymongo
import mysql.connector
import isodate
import pandas as pd
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build



def youtube_api_connect(api_key):
    youtube = build("youtube", "v3", developerKey=api_key)
    return youtube

def get_channel_data(youtube, channel_id):
    try:
        channel_request = youtube.channels().list(
            part="snippet,contentDetails,statistics",
            id=channel_id
        )
        channel_response = channel_request.execute()

        if "items" in channel_response and len(channel_response["items"]) > 0:
            channel_data = channel_response["items"][0]
            return channel_data
        else:
            return None
    except HttpError as e:
        print("An HTTP error occurred:", e)
        return None

def get_playlists_data(youtube, channel_id):
    try:
        playlists_request = youtube.playlists().list(
            part="snippet",
            channelId=channel_id,
            maxResults=50
        )
        playlists_response = playlists_request.execute()

        playlists = playlists_response.get("items", [])
        playlists_data = []
        for playlist in playlists:
            playlist_data = {
                "playlist_name": playlist["snippet"]["title"],
                "playlist_id": playlist["id"],
                "videos": []
            }

            videos_data = get_video_data(youtube, playlist["id"])
            playlist_data["videos"] = videos_data

            playlists_data.append(playlist_data)

        return playlists_data, len(playlists)
    except HttpError as e:
        print("An HTTP error occurred:", e)
        return [], 0

def get_video_data(youtube, playlist_id):
    try:
        playlist_items_request = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50
        )
        playlist_items_response = playlist_items_request.execute()

        playlist_items = playlist_items_response.get("items", [])
        video_ids = [item["snippet"]["resourceId"]["videoId"] for item in playlist_items]

        videos_data = []
        video_data_map = {}

        # Fetch video details in batches
        for i in range(0, len(video_ids), 50):
            video_ids_batch = video_ids[i:i+50]
            video_request = youtube.videos().list(
                part="snippet,contentDetails,statistics,status",
                id=",".join(video_ids_batch)
            )
            video_response = video_request.execute()

            videos = video_response.get("items", [])
            for video in videos:
                video_id = video["id"]
                video_data = video_data_map.get(video_id)

                if video_data is None:
                    tags = video["snippet"].get("tags", [])
                    duration = isodate.parse_duration(video["contentDetails"]["duration"]).total_seconds()

                    video_data = {
                        "video_id": video_id,
                        "video_title": video["snippet"]["title"],
                        "video_description": video["snippet"]["description"],
                        "tags": tags,
                        "published_at": video["snippet"]["publishedAt"],
                        "view_count": video["statistics"]["viewCount"],
                        "like_count": video["statistics"]["likeCount"],
                        "dislike_count": 0,
                        "favorite_count": video["statistics"]["favoriteCount"],
                        "comment_count": video["statistics"]["commentCount"],
                        "duration": duration,
                        "thumbnail": video["snippet"]["thumbnails"]["default"]["url"],
                        "caption_status": "Available" if video["contentDetails"]["caption"] else "Not Available",
                        "comments": get_comments_data(youtube, video_id)
                    }

                    video_data_map[video_id] = video_data

                videos_data.append(video_data)

        return videos_data
    except HttpError as e:
        print("An HTTP error occurred:", e)
        return []

def get_comments_data(youtube, video_id):
    try:
        comments_request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100
        )
        comments_response = comments_request.execute()

        comments = []
        while "items" in comments_response:
            for item in comments_response["items"]:
                comment_data = {
                    "comment_id": item["id"],
                    "comment_text": item["snippet"]["topLevelComment"]["snippet"]["textDisplay"],
                    "comment_author": item["snippet"]["topLevelComment"]["snippet"]["authorDisplayName"],
                    "comment_published_at": item["snippet"]["topLevelComment"]["snippet"]["publishedAt"]
                }
                comments.append(comment_data)

            if "nextPageToken" in comments_response:
                comments_request = youtube.commentThreads().list(
                    part="snippet",
                    videoId=video_id,
                    maxResults=100,
                    pageToken=comments_response["nextPageToken"]
                )
                comments_response = comments_request.execute()
            else:
                break

        return comments
    except HttpError as e:
        print("An HTTP error occurred:", e)
        return []


def get_multiple_channel_data(channel_ids,apikey):
    youtube = youtube_api_connect(apikey)
    channel_id_list = channel_ids.split(",")
    all_data = []
    datas = []

    for channel_id in channel_id_list:
        channel_data = get_channel_data(youtube, channel_id.strip())
        if channel_data:
            playlist_data, playlist_count = get_playlists_data(youtube, channel_id.strip())

            data = {
                    "Channel_name": channel_data["snippet"]["title"],
                    "Channel_Id": channel_data["id"],
                    "Subscription_count": channel_data["statistics"]["subscriberCount"],
                    "Channel_views": channel_data["statistics"]["viewCount"],
                    "Channel_description": channel_data["snippet"]["description"],
                    "Playlist_count": playlist_count,
                    "Playlists": playlist_data
                }
            
            c_data = data.copy()
            
            if "Playlists" in c_data:
                del c_data["Playlists"]
            
            datas.append(c_data)
            all_data.append({"channel":data})

    return datas,all_data




def store_data_mongo(alldata):
    mongourl = "mongodb+srv://prathip:1234@cluster1.ifalapx.mongodb.net/"
    try:
        with pymongo.MongoClient(mongourl) as client:
            db = client['YoutubeHacks']
            collection = db['ChannelData']
            
            inserted_channel_ids = []
            
            for i in alldata:
                
                channel_id = i["channel"]["Channel_Id"]
                filter_query = {"channel.Channel_Id": channel_id}

                if collection.count_documents(filter_query) > 0:
                    inserted_channel_ids.append(channel_id)
                else:
                    insert_result = collection.insert_one(i)

                    if insert_result.inserted_id:
                        inserted_channel_ids.append(channel_id)
                    else:
                        st.write("Failed to insert data.")
        
            #st.write(inserted_channel_ids)
            return inserted_channel_ids 
        
    except pymongo.errors.PyMongoError as e:
        st.write("An error occurred while storing data in MongoDB:", str(e))

    return None

        
def sql_connect():
    sql_host = st.secrets["DB_HOST"]
    sql_user = st.secrets["DB_USER"]
    sql_password =st.secrets["DB_PASS"]
    dbname = st.secrets["DB_NAME"]    
    sql_port = st.secrets["DB_PORT"]
    conn = mysql.connector.connect(
            host=sql_host,
            port=sql_port,
            user=sql_user,
            password=sql_password,
            database = dbname
        )
    return conn


def store_data_sql(conn,cursor,filterdata):
    try:
        if conn:
            mongourl = def store_data_mongo(alldata):
    mongourl = ["mongodb+srv://prathip:1234@cluster1.ifalapx.mongodb.net/"]
    try:
        with pymongo.MongoClient(mongourl) as client:
            db = client['YoutubeHacks']
            collection = db['ChannelData']
            
            inserted_channel_ids = []
            mongoclient = pymongo.MongoClient(mongourl)
            db = mongoclient['YoutubeHacks']
            collection = db['ChannelData']
            fields = "channel.Channel_Id"
            
            for i in filterdata:
                
                check_query = f"SELECT channel_id FROM channeldata WHERE channel_id = %s"
                cursor.execute(check_query, (i,))
                result = cursor.fetchone()

                if result:
                    print(result)
                    #continue
                    st.write("Channel Data Inserted Already! Try with another Channel")
                else:
                    document = collection.find_one({fields: i})
                    # Insert Channel data
                    channel_data = document['channel']
                    channel_values = (
                        channel_data['Channel_Id'],
                        channel_data['Channel_name'],
                        channel_data['Subscription_count'],
                        channel_data['Channel_views'],
                        channel_data['Playlist_count'],
                        channel_data['Channel_description']
                    )
                    q1 = "INSERT INTO channeldata (channel_id, channel_name, subscription_count, channel_views, playlist_count, channel_description) VALUES (%s, %s, %s, %s, %s, %s)"
                    cursor.execute(q1, channel_values)

                    # Insert Playlist Data
                    playlist_values = []
                    video_values = []
                    comment_values = []
                    
                    for playlist in channel_data['Playlists']:
                        playlist_values.append((
                            playlist['playlist_id'],
                            channel_data['Channel_Id'],
                            playlist['playlist_name']
                        ))

                        for video in playlist['videos']:
                            video_values.append((
                                video['video_id'],
                                playlist['playlist_id'],
                                video['video_title'],
                                video['video_description'],
                                video['published_at'],
                                video['view_count'],
                                video['like_count'],
                                video['comment_count'],
                                video['duration'],
                                video['thumbnail'],
                                video['caption_status']
                            ))

                            for comment in video['comments']:
                                comment_values.append((
                                    comment['comment_id'],
                                    video['video_id'],
                                    comment['comment_text'],
                                    comment['comment_author'],
                                    comment['comment_published_at']
                                ))

                    q2 = "INSERT INTO playlistdata (playlist_id, channel_id, playlist_name) VALUES (%s, %s, %s)"
                    cursor.executemany(q2, playlist_values)

                    q3 = "INSERT INTO videodata (video_id, playlist_id, video_name, video_description, published_date, view_count, like_count, comment_count, duration, thumbnail, caption_status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    cursor.executemany(q3, video_values)

                    q4 = "INSERT INTO commentdata (comment_id, video_id, comment_text, comment_author, comment_published_date) VALUES (%s, %s, %s, %s, %s)"
                    cursor.executemany(q4, comment_values)

            st.write("Channel Data Stored!")
            conn.commit()

    except mysql.connector.Error as err:
        st.write("Error: {}".format(err))

       
        
                   
def create_database(db,sql_host,sql_user,sql_pass):
    try:
        conn = mysql.connector.connect(
            host=sql_host,
            user=sql_user,
            password=sql_pass,
        )
        cursor = conn.cursor()
        cursor.execute("CREATE DATABASE {}".format(db))
        conn.close()
        conn = sql_connect()
        if conn:  
            st.write("Database created")
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()    
            dtable = ['channeldata','commentdata','playlistdata','videodata']
            for i,table in zip(dtable,tables):
                if i.lower() != table[0].lower():
                    if i=='channeldata':
                        cursor.execute("create table channeldata(channel_id varchar(255),channel_name varchar(255),subscription_count int,channel_views int,playlist_count int,channel_description text)")
                    elif i=='commentdata':
                        cursor.execute("create table commentdata(comment_id varchar(255),video_id varchar(255),comment_text text,comment_author varchar(255),comment_published_date datetime)")
                    elif i=='playlistdata':
                        cursor.execute("create table playlistdata(playlist_id varchar(255),channel_id varchar(255),playlist_name varchar(255))")
                    elif i=='videodata':
                        cursor.execute("create table videodata(video_id varchar(255),playlist_id varchar(255),video_name varchar(255),video_description text,published_date datetime,view_count int, like_count int,comment_count int,duration int,thumbnail varchar(255),caption_status varchar(255))")
            conn.close()
        return True
            
    except mysql.connector.Error as err:
        st.write("Error: {}".format(err))
        return False
    
def query_sql_data(cursor, pos):
    queries = {
        1: "SELECT vd.video_name, cd.channel_name FROM videodata AS vd JOIN playlistdata AS pd ON vd.playlist_id = pd.playlist_id JOIN channeldata AS cd ON pd.channel_id = cd.channel_id",
        2: "SELECT cd.channel_name, COUNT(vd.video_id) AS video_count FROM channeldata AS cd JOIN playlistdata AS pd ON cd.channel_id = pd.channel_id JOIN videodata AS vd ON pd.playlist_id = vd.playlist_id GROUP BY cd.channel_name ORDER BY video_count DESC",
        3: "SELECT vd.video_name, cd.channel_name, vd.view_count FROM videodata AS vd JOIN playlistdata AS pd ON vd.playlist_id = pd.playlist_id JOIN channeldata AS cd ON pd.channel_id = cd.channel_id ORDER BY vd.view_count DESC LIMIT 10",
        4: "SELECT vd.video_name, COUNT(c.comment_id) AS comment_count FROM videodata AS vd LEFT JOIN commentdata AS c ON vd.video_id = c.video_id GROUP BY vd.video_name",
        5: "SELECT vd.video_name, cd.channel_name, vd.like_count FROM videodata AS vd JOIN playlistdata AS pd ON vd.playlist_id = pd.playlist_id JOIN channeldata AS cd ON pd.channel_id = cd.channel_id WHERE (vd.like_count, cd.channel_id) IN ( SELECT MAX(v.like_count), p.channel_id FROM videodata AS v JOIN playlistdata AS p ON v.playlist_id = p.playlist_id GROUP BY p.channel_id ) ORDER BY vd.like_count DESC",
        6: "SELECT vd.video_name, cd.channel_name, vd.like_count FROM videodata AS vd JOIN playlistdata AS pd ON vd.playlist_id = pd.playlist_id JOIN channeldata AS cd ON pd.channel_id = cd.channel_id ORDER BY vd.like_count DESC",
        7: "SELECT cd.channel_name, SUM(vd.view_count) AS total_views FROM channeldata AS cd JOIN playlistdata AS pd ON cd.channel_id = pd.channel_id JOIN videodata AS vd ON pd.playlist_id = vd.playlist_id GROUP BY cd.channel_name",
        8: "SELECT DISTINCT cd.channel_name FROM channeldata AS cd JOIN playlistdata AS pd ON cd.channel_id = pd.channel_id JOIN videodata AS vd ON pd.playlist_id = vd.playlist_id WHERE YEAR(STR_TO_DATE(vd.published_date, '%Y-%m-%dT%H:%i:%sZ')) = 2022",
        9: "SELECT cd.channel_name, AVG(vd.duration) AS average_duration FROM channeldata AS cd JOIN playlistdata AS pd ON cd.channel_id = pd.channel_id JOIN videodata AS vd ON pd.playlist_id = vd.playlist_id GROUP BY cd.channel_name",
        10: "SELECT vd.video_name, cd.channel_name, COUNT(cm.comment_id) AS comment_count FROM videodata AS vd JOIN playlistdata AS pd ON vd.playlist_id = pd.playlist_id JOIN channeldata AS cd ON pd.channel_id = cd.channel_id JOIN commentdata AS cm ON vd.video_id = cm.video_id GROUP BY vd.video_name, cd.channel_name ORDER BY comment_count DESC"
    }

    if pos in queries:
        query = queries[pos]
        cursor.execute(query)
        rows = cursor.fetchall()
        df = pd.DataFrame(rows, columns=cursor.column_names)
        df.index = df.index + 1
        return df
    else:
        return None

    


def main():
    st.header("Youtube Hacks")
    
    tab1, tab2, tab3 = st.tabs(["Data", "Table","Query"])
    
    conn = sql_connect()
    cursor = conn.cursor()
    
    with tab1:
        st.header("Fetch Data")
        apikey = st.text_input("API Key:")
        c_id = st.text_input("Channel ID:")
        
        if c_id and apikey:
            chdata, alldata = get_multiple_channel_data(c_id,apikey)
            st.json(chdata)
            
            if st.button("Store Data"):
                filterdata = store_data_mongo(alldata)
                store_data_sql(conn,cursor,filterdata)
                
                
    with tab2:
        st.header("Table")
        
        if conn:
            q1 = "SELECT * FROM channeldata"
            cursor.execute(q1)
            rows = cursor.fetchall()

            # Convert the rows to a DataFrame
            df = pd.DataFrame(rows, columns=cursor.column_names)
            df.index = df.index + 1

            # Display the DataFrame as a table in Streamlit
            st.write("Channels List")
            
            table_style = f"""
                <style>
                    .dataframe tbody tr {{
                        height: 30px;
                    }}
                    .dataframe table {{
                        height: 200px;
                        width: 1000px;
                    }}
                    .dataframe thead th:first-child,
                    .dataframe tbody tr:first-child {{
                        background-color: #f2f2f2;
                        position: sticky;
                        top: 0;
                        z-index: 1;
                    }}
                </style>
            """
            st.markdown(table_style, unsafe_allow_html=True)
            st.dataframe(df)
            
            
            q2 = "SELECT * FROM playlistdata"
            cursor.execute(q2)
            playlist_rows = cursor.fetchall()
            playlist_df = pd.DataFrame(playlist_rows, columns=cursor.column_names)
            playlist_df.index = playlist_df.index + 1
            st.write("Playlist List")
            st.dataframe(playlist_df)

            q3 = "SELECT * FROM videodata"
            cursor.execute(q3)
            video_rows = cursor.fetchall()
            video_df = pd.DataFrame(video_rows, columns=cursor.column_names)
            video_df.index = video_df.index + 1
            st.write("Video List")
            st.dataframe(video_df)

            q4 = "SELECT * FROM commentdata"
            cursor.execute(q4)
            comment_rows = cursor.fetchall()
            comment_df = pd.DataFrame(comment_rows, columns=cursor.column_names)
            comment_df.index = comment_df.index + 1
            st.write("Comment List")
            st.dataframe(comment_df)
            
        
    
    with tab3:
        st.header("Query")
        
        options = [
            "Select a Question from the List",
            "What are the names of all the videos and their corresponding channels?",
            "Which channels have the most number of videos, and how many videos do they have?",
            "What are the top 10 most viewed videos and their respective channels?",
            "How many comments were made on each video, and what are their corresponding video names?",
            "Which videos have the highest number of likes, and what are their corresponding channel names?",
            "What is the total number of likes and dislikes for each video, and what are their corresponding video names?",
            "What is the total number of views for each channel, and what are their corresponding channel names?",
            "What are the names of all the channels that have published videos in the year 2022?",
            "What is the average duration of all videos in each channel, and what are their corresponding channel names?",
            "Which videos have the highest number of comments, and what are their corresponding channel names?"
        ]
        
        selected_option = st.selectbox("Ask a Question:", options)

        # Get the position of the selected option
        position = options.index(selected_option)
        
        retriveddata = query_sql_data(cursor,position)
        
        st.table(retriveddata)
        
if __name__ == "__main__":
    main()

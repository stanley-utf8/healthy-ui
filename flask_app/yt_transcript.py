import http.client
import json
from youtube_transcript_api import YouTubeTranscriptApi
import go_interface
import re
import keyword_ex

trk = keyword_ex.TextRankKeyword()


def get_most_replayed_sections(video_id):
    conn = http.client.HTTPSConnection("yt.lemnoslife.com")

    headersList = { 
    "Accept": "*/*",
    }

    payload = ""

    conn.request("GET", f"/videos?part=mostReplayed&id={video_id}", payload, headersList)
    response = conn.getresponse()
    result = response.read()

    # print(result.decode("utf-8"))
    result_json = json.loads(result.decode("utf-8"))

    return result_json

def get_peak_rewatched_timestamps(result_json, video_id):
    markers = result_json[video_id]['MostReplayed']['items'][0]['mostReplayed']['markers']
    sorted_markers = sorted(markers, key=lambda x: x['intensityScoreNormalized'], reverse=True)    
    top_markers = sorted_markers[:10]
    top_timestamps_seconds = [marker['startMillis'] / 1000 for marker in top_markers]
    # top_timestamps_minutes = [marker['startMillis'] / 1000 / 60 for marker in top_markers]
    return top_timestamps_seconds

def get_transcript(video_id):
    # Only English Manual and Auto transcripts, translating error handling would take too long
    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)    
    
    try:
        # try to find manual transcript 'en' then 'en-US' then autogenerated
        transcript_manual = transcript_list.find_manually_created_transcript(['en', 'en-US'])
        if transcript_manual is not None:
            print("manual transcript found")
            # print(transcript_manual.fetch())
            # if timestamps is not None:
            transcript_manual = transcript_manual.fetch()
            transcript_manual = clean_transcript(transcript_manual)
            return (transcript_manual, "manual") # with timestamps
            # else:
            #     transcript_manual = transcript_manual.translate(['en, en-US']).fetch()[0]['text']
            #     return (transcript_manual, "manual") # without timestamps
    except Exception as e:
        print("No English manual transcript found")
        try:
            transcript_auto = transcript_list.find_generated_transcript(['en', 'en-US'])

            if transcript_auto is not None:
                print("auto transcript found")
                return (transcript_auto.fetch(), "auto") # with timestamps

        except Exception as e:
            print("No english auto transcript found")
            try: 
                for transcript in transcript_list:
                    if transcript.is_translatable:
                        try:
                            transcript = transcript.translate('en') 
                            return (transcript.fetch(), "translated") # with timestamps
                        except Exception as e:
                            print("Not translatable to English")
            except Exception as e:
                print("No transcripts found")

    return {}, "none"
        

def clean_transcript(transcript):
    print("cleaning transcript")
    for entry in transcript:
        # Remove all newlines
        entry['text'] = re.sub(r'\n', ' ', entry['text'])
        # Remove escape characters
        entry['text'] = re.sub(r'\\', '', entry['text'])
        # Remove non-breaking spaces
        entry['text'] = entry['text'].replace('\xa0', ' ')
        # Remove extra spaces
        entry['text'] = re.sub(r'\s+', ' ', entry['text']).strip()
    return transcript

def concatenate_transcript(transcript):
    concatenated_transcript = ''.join([entry['text'] for entry in transcript])
    return concatenated_transcript


def find_close_entries(timestamps, transcript, tolerance_sec=20):
    def binary_search(arr, x):
        left, right = 0, len(arr) - 1
        while left <= right:
            mid = (left + right) // 2
            if arr[mid]['start'] < x: 
                left = mid + 1
            elif arr[mid]['start'] > x:
                right = mid - 1
            else:
                return mid # exact match to timestamp

        # No exact match, return closest insertion point
        # Handles cases when x > all values in list
        return left if left < len(arr) else right

    print(f"Processing with tolerance: {tolerance_sec}s")    

    result = []
    last_processed_time = float("-inf")
    timestamp_order = {t: i for i, t in enumerate(timestamps)}

    for timestamp in sorted(timestamps):
        print(f"\nProcessing timestamp: {timestamp}")
        
        current_threshold = timestamp - tolerance_sec

        start_time = max(current_threshold if current_threshold >= 0 else 0, last_processed_time)

        print(f"  Searching from time: {start_time}")

        start_index = binary_search(transcript, start_time)
        # close_entries = []

        # Walk entries before closest match until outside threshold
        i = start_index

        # Walk entries after closest match
        while i < len(transcript) and transcript[i]['start'] <= timestamp + tolerance_sec:
            entry = transcript[i]
            result.append({**entry, "close_values" : [timestamp], "sort_key" : timestamp_order[timestamp]})
            i += 1
        
        last_processed_time = timestamp + tolerance_sec
        print(f"  Updated last processed time to: {last_processed_time}")

    return result

def sort_entries(entries, timestamps, option="asc"):
    if option == "pop": 
        entries = sorted(entries, key=lambda x: x['sort_key']) 

    relevant_transcript = ''
    for entry in entries:
        # reorder to match close_values to order of timestamps
        print(f"Entry: {entry['text']}, start: {entry['start']}, close values: {entry['close_values']}")
        relevant_transcript += (" " + entry['text'])

    return relevant_transcript

def get_relevant_transcript(video_ids, tolerance_sec=20, option="asc"):
    # Splice link, Convert to bytes for C functions

    res = go_interface.youtube_transcript_most_replayed_cc(video_ids)
   

    transcript_list = {}
    for byte_id in video_ids: 
        video_id = byte_id.decode('utf-8')

        assert res != None, "Error in fetching most replayed cc from go interface"

        # Handle case where transcript is empty
        if res[video_id]["Transcript"]["transcript"] == None:
            transcript_list[video_id] = {
                "text": None,
                "source": None
            }
            continue

        timestamps = None
        if res[video_id]["MostReplayed"]["items"] is not None:
            if res[video_id]["MostReplayed"]["items"][0]["mostReplayed"]["markers"] is not None:
                try:
                    timestamps = get_peak_rewatched_timestamps(res, video_id)
                    print(timestamps)
                except Exception as e:
                    print("No peak rewatched timestamps found")
                    timestamps = None

        if timestamps is not None:
            entries = find_close_entries(timestamps, res[video_id]["Transcript"]["transcript"], tolerance_sec=tolerance_sec) # Default returns ascending
            relevant_transcript = sort_entries(entries, timestamps)
            transcript_list[video_id] = {
                "text": relevant_transcript,
                "source": res[video_id]["Transcript"]["source"]
            }
        else:
            # no timestamps to compare, concatenate transcipt
            concatenated_transcript = concatenate_transcript(res[video_id]["Transcript"]["transcript"])
            transcript_list[video_id] = {
                "text": concatenated_transcript,
                "source": res[video_id]["Transcript"]["source"]
            }

    return transcript_list

def extract_ids(video_ids):
    for i, video_id in enumerate(video_ids):
        if "/" in video_id:
            video_id = video_id.split("?v=")[-1].split("&t=")[0] if "&t=" in video_id else video_id.split("?v=")[-1]
            print(f"video_id: {video_id}")

        byte_id = video_id.encode('utf-8')
        # replace in-place
        video_ids[i] = byte_id
    return video_ids

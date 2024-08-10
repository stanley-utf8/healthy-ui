import http.client
import json
from youtube_transcript_api import YouTubeTranscriptApi


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

def get_peak_rewatched_timestamps(result_json):
    markers = result_json['items'][0]['mostReplayed']['markers']
    sorted_markers = sorted(markers, key=lambda x: x['intensityScoreNormalized'], reverse=True)    
    top_markers = sorted_markers[:10]
    top_timestamps_seconds = [marker['startMillis'] / 1000 for marker in top_markers]
    # top_timestamps_minutes = [marker['startMillis'] / 1000 / 60 for marker in top_markers]
    return top_timestamps_seconds

def get_transcript(video_id):
    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

    try:
        transcript_manual = transcript_list.find_manually_created_transcript(['en'])  
        if transcript_manual is not None:
            print(transcript_manual.fetch())
            print(transcript_manual.translate('en').fetch())

    except Exception as e:
        print("No manual transcript found")

    try:
        transcript_auto = transcript_list.find_generated_transcript(['en'])
        if transcript_auto is not None:
            return (transcript_auto.fetch()) # with timestamps
            # print(transcript_auto.translate('en').fetch()) # without timestamps

    except Exception as e:
        print("No auto transcript found")


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


video_id = '1KsghMTtgig'

res = get_most_replayed_sections(video_id)
timestamps = get_peak_rewatched_timestamps(res)
print(timestamps)
transcript = get_transcript(video_id)
entries = find_close_entries(timestamps, transcript) # Default returns ascending
relevant_transcript = sort_entries(entries, timestamps)
print(relevant_transcript)


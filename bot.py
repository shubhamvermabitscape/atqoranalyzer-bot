from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import ChannelAccount
from config import DefaultConfig
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient   
from queue import Queue
from threading import Thread

CONFIG = DefaultConfig()


class MyBot(ActivityHandler):
    
    def __init__(self):
        self.client = AzureOpenAI(
            azure_endpoint=CONFIG.AZURE_OPENAI_ENDPOINT,
            api_key=CONFIG.AZURE_OPENAI_API_KEY,
            api_version=CONFIG.AZURE_OPENAI_API_VERSION
        )
        self.credential = AzureKeyCredential(CONFIG.SEARCH_API_KEY)
        self.MAX_CONVERSATIONS = 10


    def search_query_in_index(self, queue, index_name, query):
        print(index_name)
        search_url = f"https://{CONFIG.SEARCH_SERVICE_NAME}.search.windows.net/"
        search_client = SearchClient(endpoint=search_url, index_name=index_name, credential=self.credential)
    
        results = search_client.search(search_text=query, top=1)  
    
        content = []
        for result in results:
            for field, value in result.items():
                content.append(f"{field}: {value}")
        queue.put(" ".join(content))
    
    def search_query_in_azure(self, query):
        queue = Queue()
        threads = []
    
        for index_name in CONFIG.SEARCH_INDEX_NAME:
            thread = Thread(target=self.search_query_in_index, args=(queue, index_name, query))
            threads.append(thread)
            thread.start()
    
        for thread in threads:
            thread.join()
    
        results = []
        while not queue.empty():
            results.append(queue.get())
    
        return " ".join(results)
    
    def generate_response_with_azure_openai(self, user_query, search_result):
        message_text = [
            {"role": "system", "content": "The following is a query from a user and the results fetched from Azure's search indexes, and give page number also in rensponse."},
            {"role": "user", "content": user_query},
            {"role": "assistant", "content": search_result}
        ]
    
        completion = self.client.chat.completions.create(
            model="gpt-4-turbo",
            messages=message_text,
            temperature=0.7,
            max_tokens=4096,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0,
            stop=None
        )
        return completion.choices[0].message.content if completion.choices else "Sorry, I couldn't generate a response."

    async def on_message_activity(self, turn_context: TurnContext):
        search_result = self.search_query_in_azure(turn_context.activity.text)
        print(search_result)
        if search_result:
            response = self.generate_response_with_azure_openai(turn_context.activity.text, search_result)
            if response:
                await turn_context.send_activity(response)

    async def on_members_added_activity(
        self,
        members_added: [ChannelAccount],
        turn_context: TurnContext
    ):
        for member_added in members_added:
            if member_added.id != turn_context.activity.recipient.id:
                await turn_context.send_activity("Hello and welcome!")


from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
import re

def preprocess_text(text):
    """Perform text preprocessing"""
    try:
        text = text.lower()
        text = re.sub(r'[^a-zA-Z\s]', '', text)
        tokens = word_tokenize(text)
        stop_words = set(stopwords.words('english'))
        tokens = [token for token in tokens if token not in stop_words and len(token) > 1]
        lemmatizer = WordNetLemmatizer()
        tokens = [lemmatizer.lemmatize(token) for token in tokens]
        processed_text = ' '.join(tokens)
        return processed_text
    except Exception as e:
        print(f"Error in preprocessing: {e}")
        return text

def calculate_cosine_similarity(vec1, vec2):
    """Calculate cosine similarity between two vectors"""
    from sklearn.metrics.pairwise import cosine_similarity
    return cosine_similarity(vec1, vec2)[0][0]
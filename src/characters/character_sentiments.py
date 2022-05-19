# with helper functions from
# https://github.com/hzjken/character-network

import os
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from afinn import Afinn
from nltk.tokenize import sent_tokenize
from sklearn.feature_extraction.text import CountVectorizer

from name_entity_recognition import name_entity_recognition
from utils import read_story
import json

data_folder = Path(os.getcwd()) / 'data/aesop/original'

target_dir_net = "data/net"
target_sentiment_dir = 'res/aesop/sentiments'


def calculate_align_rate(sentence_list):
    '''
    Function to calculate the align_rate of the whole novel
    :param sentence_list: the list of sentence of the whole novel.
    :return: the align rate of the novel.
    '''
    afinn = Afinn()
    sentiment_score = [afinn.score(x) for x in sentence_list]
    align_rate = np.sum(sentiment_score) / len(np.nonzero(sentiment_score)[0]) * -2

    return align_rate


def calculate_matrix(name_list, sentences, cor_res_sentences, align_rate):
    '''
    Function to calculate the co-occurrence matrix and sentiment matrix among all the top characters
    :param name_list: the list of names of the top characters in the novel.
    :param sentences: the list of sentences in the novel.
    :param align_rate: the sentiment alignment rate to align the sentiment score between characters due to the writing style of
    the author. Every co-occurrence will lead to an increase or decrease of one unit of align_rate.
    :return: the co-occurrence matrix and sentiment matrix.
    '''

    # calculate a sentiment score for each sentence in the novel
    afinn = Afinn()
    sentiment_score = [afinn.score(x) for x in sentences]

    # replace name occurrences with names that can be vectorized
    for i in range(len(cor_res_sentences)):
        cor_res_sentences[i] = cor_res_sentences[i].lower()

        for name in name_list:
            tmp = name.split(" ")
            tmp = "_".join(tmp)
            cor_res_sentences[i] = cor_res_sentences[i].replace(name, tmp)

    for i in range(len(name_list)):
        tmp = name_list[i].split(" ")
        name_list[i] = "_".join(tmp)

    name_vec = CountVectorizer(vocabulary=name_list, binary=True)

    # calculate occurrence matrix and sentiment matrix among the top characters
    occurrence_each_sentence = name_vec.fit_transform(cor_res_sentences).toarray()
    co_occurrence_matrix = np.dot(occurrence_each_sentence.T, occurrence_each_sentence)
    sentiment_matrix = np.dot(occurrence_each_sentence.T, (occurrence_each_sentence.T * sentiment_score).T)
    sentiment_matrix += align_rate * co_occurrence_matrix
    co_occurrence_matrix = np.tril(co_occurrence_matrix)
    sentiment_matrix = np.tril(sentiment_matrix)

    # diagonals of the matrices are set to be 0 (co-occurrence of name itself is meaningless)
    shape = co_occurrence_matrix.shape[0]
    co_occurrence_matrix[[range(shape)], [range(shape)]] = 0
    sentiment_matrix[[range(shape)], [range(shape)]] = 0

    # get character sentiments
    character_sentiments = (np.sum(occurrence_each_sentence.T * sentiment_score, axis=1)).T
    # normalize
    divisor = np.abs(character_sentiments).max()
    if divisor == 0:
        divisor = 1
    character_sentiments = character_sentiments / divisor

    return co_occurrence_matrix, sentiment_matrix, character_sentiments

def matrix_to_edge_list(matrix, mode, name_list):
    '''
    Function to convert matrix (co-occurrence/sentiment) to edge list of the network graph. It determines the
    weight and color of the edges in the network graph.
    :param matrix: co-occurrence matrix or sentiment matrix.
    :param mode: 'co-occurrence' or 'sentiment'
    :param name_list: the list of names of the top characters in the novel.
    :return: the edge list with weight and color param.
    '''
    edge_list = []
    shape = matrix.shape[0]
    lower_tri_loc = list(zip(*np.where(np.triu(np.ones([shape, shape])) == 0)))
    normalized_matrix = matrix / np.max(np.abs(matrix))

    if mode == 'co-occurrence':
        weight = np.log(2000 * normalized_matrix + 1) * 0.7
        color = np.log(2000 * normalized_matrix + 1)
    if mode == 'sentiment':
        weight = np.log(np.abs(1000 * normalized_matrix) + 1) * 0.7
        color = 2000 * normalized_matrix
    if mode == 'bare':
        weight = np.log(np.abs(1000 * normalized_matrix) + 1) * 0.7
        color = 2000 * normalized_matrix
    for i in lower_tri_loc:
        # print('edge weight', weight[i])
        if (mode != 'bare' or weight[i] > 0.0001):
            edge_list.append((name_list[i[0]], name_list[i[1]], {'weight': weight[i], 'color': color[i]}))

    return edge_list

def plot_graph(name_list, name_frequency, matrix, plt_name, suffix, mode, path=''):
    '''
    Function to plot the network graph (co-occurrence network or sentiment network).
    :param name_list: the list of top character names in the novel.
    :param name_frequency: the list containing the frequencies of the top names.
    :param matrix: co-occurrence matrix or sentiment matrix.
    :param plt_name: the name of the plot (PNG file) to output.
    :param mode: 'co-occurrence' or 'sentiment'
    :param path: the path to output the PNG file.
    :return: a PNG file of the network graph.
    '''

    label = {i: i for i in name_list}
    edge_list = matrix_to_edge_list(matrix, mode, name_list)
    normalized_frequency = np.array(name_frequency) / np.max(name_frequency)

    plt.figure(figsize=(20, 20))
    G = nx.Graph()
    G.add_nodes_from(name_list)
    G.add_edges_from(edge_list)
    pos = nx.circular_layout(G)
    edges = G.edges()
    weights = [G[u][v]['weight'] for u, v in edges]
    colors = [G[u][v]['color'] for u, v in edges]

    if mode == 'bare':
        nx.write_gexf(G, f'{target_dir_net}/{plt_name}_characters.gexf')
    elif mode == 'sentiment':
        nx.write_gexf(G, f'{target_dir_net}/{plt_name}_character_sentiment.gexf')

    if mode == 'co-occurrence':
        nx.draw(G, pos, node_color='#A0CBE2', node_size=np.sqrt(normalized_frequency) * 4000, edge_cmap=plt.cm.Blues,
                linewidths=10, font_size=35, labels=label, edge_color=colors, with_labels=True, width=weights)
    elif mode == 'sentiment':
        nx.draw(G, pos, node_color='#A0CBE2', node_size=np.sqrt(normalized_frequency) * 4000,
                linewidths=10, font_size=35, labels=label, edge_color=colors, with_labels=True,
                width=weights, edge_vmin=-1000, edge_vmax=1000)
    elif mode == 'bare':
        nx.draw(G, pos, node_color='#A0CBE2', node_size=np.sqrt(normalized_frequency) * 4000,
                linewidths=10, font_size=35, labels=label, with_labels=True, edge_vmin=-1000, edge_vmax=1000)
    else:
        raise ValueError("mode should be either 'bare', 'co-occurrence', or 'sentiment'")

    plt.savefig('characterR/graphs/' + plt_name + suffix + '.png')

    return G

def get_top_10_pagerank(G):
    N = G.number_of_nodes()
    pgrnk = nx.pagerank(G)
    pgrnk.update((key, value / (N - 1)) for key, value in pgrnk.items())

    sorted_pgrnk = sorted(pgrnk.items(), key=lambda item: item[1], reverse=True)[:10]
    return sorted_pgrnk

def get_pagerank_leads(G, character_sentiments, spaced_characters):
    top_10_pagerank = get_top_10_pagerank(G)

    protagonist = None
    antagonist = None
    for name, rank in top_10_pagerank:
        name_idx = spaced_characters.index(name)
        sentiment = rank * character_sentiments[name_idx]
        if protagonist is None and sentiment > 0:
            protagonist = name
        if antagonist is None and sentiment < 0:
            antagonist = name
        if protagonist is not None and antagonist is not None:
            break
    
    return protagonist, antagonist

def get_sentiment_leads(character_sentiments, spaced_characters):
    protagonist = None
    antagonist = None

    protagonist_idx = np.argmax(character_sentiments)
    antagonist_idx = np.argmin(character_sentiments)

    if (protagonist_idx >= 0 and character_sentiments[protagonist_idx] > 0):
        protagonist = spaced_characters[protagonist_idx]
    if (antagonist_idx >= 0 and character_sentiments[antagonist_idx] < 0):
        antagonist = spaced_characters[antagonist_idx]

    return protagonist, antagonist

def save_character_sentiments(sentiment_matrix, spaced_characters):
    divisor = np.abs(sentiment_matrix).max()
    if (divisor == 0):
        divisor = 1

    sentiments = {}
    for i in range(len(spaced_characters)):
        sentiments[spaced_characters[i]] = {}
        for j in range(len(spaced_characters)):
            sentiments[spaced_characters[i]][spaced_characters[j]] = sentiment_matrix[i, j] / divisor

    res_file = f'{target_sentiment_dir}/{name}.json'
    with open(res_file, 'w') as file:
        json.dump({
            'sentiments': sentiments
        }, file, indent=4)

def character_sentiments(doc):
    characters, character_counts, cor_res_doc = name_entity_recognition(doc)

    sentences = sent_tokenize(doc)
    cor_res_sentences = sent_tokenize(cor_res_doc)
    align_rate = calculate_align_rate(sentences)

    co_occurrence_matrix, sentiment_matrix, character_sentiments = calculate_matrix(characters, sentences, cor_res_sentences, align_rate)

    spaced_characters = [' '.join(x.split('_')) for x in characters]

    # plot co-occurrence and sentiment graph
    plot_graph(spaced_characters, character_counts, co_occurrence_matrix, name, ' co-occurrence graph', 'co-occurrence')
    sentiment_graph = plot_graph(spaced_characters, character_counts, sentiment_matrix, name, ' sentiment graph', 'sentiment')
    plot_graph(spaced_characters, character_counts, sentiment_matrix, name, ' bare graph', 'bare')

    save_character_sentiments(sentiment_matrix + sentiment_matrix.T, spaced_characters)

    pr_protagonist, pr_antagonist = get_pagerank_leads(sentiment_graph, character_sentiments, spaced_characters)
    sent_protagonist, sent_antagonist = get_sentiment_leads(character_sentiments, spaced_characters)
    print(f'PageRank leads: protagonist = "{pr_protagonist}", antagonist = "{pr_antagonist}"')
    print(f'Sentiment leads: protagonist = "{sent_protagonist}", antagonist = "{sent_antagonist}"')


if __name__ == '__main__':
    name = 'The_Sick_Lion'
    short_story = read_story(name, data_folder)

    character_sentiments(short_story)


'''
    # loop over all stories
    short_stories = []
    for filename in os.listdir(data_folder):
        if filename.endswith(".txt"):
            short_stories.append(filename)

    for name in short_stories:
        short_story = read_story(name, data_folder)
        sentence_list = sent_tokenize(short_story)
        align_rate = calculate_align_rate(sentence_list)
        preliminary_name_list = iterative_NER(sentence_list)
        name_frequency, name_list = top_names(preliminary_name_list, short_story, 20)
        co_occurrence_matrix, sentiment_matrix, _ = calculate_matrix(name_list, sentence_list, align_rate)
        # plot co-occurrence and sentiment graph
        plot_graph(name_list, name_frequency, co_occurrence_matrix, name + ' co-occurrence graph', 'co-occurrence')
        plot_graph(name_list, name_frequency, sentiment_matrix, name + ' sentiment graph', 'sentiment')
    '''

import random
import sys
import dynet as dy
import pickle
import numpy as np

epochs = 5
iteration_till_dev_size = 500 #num sentences
hid_layer = 50
top_hidden_layer = 60
out_layer = 5
tags = ()
EMB_SIZE = 50
BILSTM_INPUT = 50
CHAR_EMB_SIZE = 50
unk_word = "*UNK*"

class LstmAcceptor(object):
    def __init__(self, in_dim, lstm_dim, model):
        self.builder = dy.VanillaLSTMBuilder(1, in_dim, lstm_dim, model)
    def __call__(self, sequence):
        lstm = self.builder.initial_state()
        outputs = lstm.transduce(sequence)
        return  outputs[-1]

class BiLstm(object):
    def __init__(self, repr, emb_dim, hidden_dim, top_hidd_dim, model, out_dim):
        self.repr = repr
        self.model = model
        self.forward_top_builder = dy.VanillaLSTMBuilder(1, 2*hidden_dim, top_hidd_dim, model)
        self.forward_bot_builder = dy.VanillaLSTMBuilder(1, emb_dim, hidden_dim, model)
        self.backward_top_builder = dy.VanillaLSTMBuilder(1, 2*hidden_dim, top_hidd_dim, model)
        self.backward_bot_builder = dy.VanillaLSTMBuilder(1, emb_dim, hidden_dim, model)
        self.W = self.model.add_parameters((out_dim, 2*top_hidd_dim), init="uniform", scale = 0.8)
        if repr == "d":
            self.U = self.model.add_parameters((BILSTM_INPUT, BILSTM_INPUT+CHAR_EMB_SIZE), init="uniform", scale = 0.8)
            self.lstm = LstmAcceptor(CHAR_EMB_SIZE, BILSTM_INPUT, self.model)
        if repr == "b":
            self.lstm = LstmAcceptor(CHAR_EMB_SIZE, BILSTM_INPUT, self.model)
    def __call__(self, sequence):
        forward_top_lstm = self.forward_top_builder.initial_state()
        forward_bot_lstm = self.forward_bot_builder.initial_state()
        backward_top_lstm = self.backward_top_builder.initial_state()
        backward_bot_lstm = self.backward_bot_builder.initial_state()
        #W = self.W.expr() # convert the parameter into an Expession (add it to graph)
        W = dy.parameter(self.W)
        sequence = self.__get_vec_by_rep__(sequence)
        f_outputs = forward_bot_lstm.transduce(sequence)
        b_outputs = backward_bot_lstm.transduce(sequence[::-1])
        new_outs = []
        for f, b in zip(f_outputs, reversed(b_outputs)):
            new_outs.append(dy.concatenate([f, b]))
        f_outputs = forward_top_lstm.transduce(new_outs)
        b_outputs = backward_top_lstm.transduce(new_outs[::-1])
        new_outs = []
        for f, b in zip(f_outputs, reversed(b_outputs)):
            new_outs.append(dy.softmax((W * dy.concatenate([f, b]))))
        return new_outs

    def __get_vec_by_rep__(self, sequence):
        seq_rep = []
        for w in sequence:
            if self.repr == "a":
                seq_rep.append(embeds[voc[w]])
            elif self.repr == "b":
                vecs = [embeds[voc[char]] for char in w]
                res = self.lstm(vecs)
                seq_rep.append(res)
            elif self.repr == "c":
                w_embed = embeds[voc[w[1]]]
                sub_word = w_embed+w_embed+w_embed if len(w[1]) <= 3 else embeds[voc[w[0]]]+w_embed+embeds[voc[w[2]]]
                seq_rep.append(sub_word)
            elif self.repr == "d":
                U = self.U.expr()
                vecs = [embeds[voc[char]] for char in w[1]]
                char_out = self.lstm(vecs)
                seq_rep.append(U*(dy.concatenate([embeds[voc[w[0]]], char_out])))
        return seq_rep

def train(d_set, epochs):
    sum_of_losses = 0.0
    correct = 0.0
    sentence_idx = 0
    ner_labels = 0
    words_so_far = 0
    print("Performing train")
    for epoch in range(epochs):
        #random.shuffle(set)
        for i, (sequence, labels) in enumerate(d_set):
            dy.renew_cg()  # new computation graph
            preds = bilstm(sequence)
            local_losses = []
            for pred,label in zip(preds,labels):
                y_hat = np.argmax(pred.npvalue())
                if data_set == "ner":
                    correct += 1 if y_hat == label and label != tags["O"] else 0
                    ner_labels += 1 if (y_hat == label and label != tags["O"]) or (y_hat != label) else 0
                else:
                    correct += 1 if y_hat == label else 0
                loss = -dy.log(dy.pick(pred, label))
                local_losses.append(loss)
            words_so_far += len(preds)
            # update network by sentence loss
            sent_loss = dy.esum(local_losses)
            sum_of_losses += sent_loss.scalar_value()
            sent_loss.backward()
            trainer.update()
            if sentence_idx == iteration_till_dev_size:
                sentence_idx=0
                test()
            else:
                sentence_idx +=1
        print ("train loss: {0}".format(sum_of_losses / len(d_set)))
        if data_set == "ner":
            print("train accuracy: {0}".format((correct / ner_labels) * 100))
        else:
            print("train accuracy: {0}".format((correct / words_so_far) * 100))
        sum_of_losses = 0.0
        correct = 0.0
        words_so_far = 0
        # if epoch == 1:
        #     trainer.set_learning_rate(0.001)
        # #     trainer.learning_rate = 0.001
        if epoch == 3:
            trainer.learning_rate = 0.0005
        if epoch == 4:
            trainer.learning_rate = 0.0002
        print(trainer.learning_rate)

def test():
    correct = 0.0
    words_so_far = 0
    ner_labels = 0
    for sequence, labels in dev_set:
        dy.renew_cg()
        preds = bilstm(sequence)

        for (pred,label) in zip(preds,labels):
            y_hat = np.argmax(pred.npvalue())
            if data_set == "ner":
                correct += 1 if y_hat == label and label != tags["O"] else 0
                ner_labels += 1 if (y_hat == label and label != tags["O"]) or (y_hat != label) else 0
            else:
                correct += 1 if y_hat == label else 0
        words_so_far += len(preds)
    if data_set == "ner":
        print("dev accuracy: {0}".format((correct / ner_labels) * 100))
    else:
        print("dev accuracy: {0}".format((correct/words_so_far)*100))

def init_params_by_dataset(data_set):
    global out_layer, tags
    tags_file = "ner_tags" if data_set == "ner" else "pos_tags"
    with open(tags_file, "rb") as f:
        tags = pickle.load(f)
    out_layer = len(tags)

def init_params_by_rep(rep, trainFile):
    if rep == "a":
        voc, train_set = build_a_rep(trainFile, False)
        _, dev_set = build_a_rep(data_set+"/dev", True, voc)
    elif rep == "b":
        voc, train_set = build_b_rep(trainFile,False)
        _, dev_set = build_b_rep(data_set + "/dev", True, voc)
    elif rep == "c":
        voc, train_set = build_c_rep(trainFile, False)
        _, dev_set = build_c_rep(data_set + "/dev", True, voc)
    elif rep == "d":
        voc, train_set = build_d_rep(trainFile, False)
        _, dev_set = build_d_rep(data_set + "/dev", True, voc)
    voc[unk_word] = len(voc)
    #embeds = m.add_lookup_parameters((len(voc), EMB_SIZE), init="normal", mean = 0, std = 1)
    embeds = m.add_lookup_parameters((len(voc), EMB_SIZE))
    return voc, embeds, train_set, dev_set

#-----------------Representation REGION
def build_a_rep(trainFile, test, train_voc=None):
    voc, examples = build_vocab(trainFile, vocab_by_word, test, train_voc)
    return voc, examples

def build_b_rep(trainFile, test, train_voc=None):
    global CHAR_EMB_SIZE, EMB_SIZE
    EMB_SIZE = CHAR_EMB_SIZE
    voc, examples = build_vocab(trainFile, vocab_by_letter, test, train_voc)
    return voc, examples

def build_c_rep(trainFile, test, train_voc=None):
    voc, examples = build_vocab(trainFile, vocab_by_sub_word, test, train_voc)
    return voc, examples

def build_d_rep(trainFile, test, train_voc=None):
    global CHAR_EMB_SIZE, EMB_SIZE
    EMB_SIZE = CHAR_EMB_SIZE
    voc, examples = build_vocab(trainFile, vocab_by_word_letter, test, train_voc)
    return voc, examples

#-----------------vocab add functions REGION
def vocab_by_letter(voc, word, tag, test = False):
    examples = []
    for w in word:
        if w not in voc:
            if test:
                w = unk_word
            else:
                voc[w] = len(voc)
        examples.append(w)
    return [examples]

def vocab_by_sub_word(voc,word,tag, test = False):
    if word not in voc:
        if test:
            word = unk_word
        else:
            voc[word] = len(voc)
    if len(word) <= 3:
        return [(word,word,word)]
    pre = word[0:3]
    if word[0:3] not in voc:
        if test:
            pre = unk_word
        else:
            voc[pre] = len(voc)

    post = word[len(word) - 3:len(word)]
    if word[len(word) - 3:len(word)] not in voc:
        if test:
            post = unk_word
        else:
            voc[post] = len(voc)
    return [(pre, word, post)]


def vocab_by_word_letter(voc, word, tag, test = False):
    w_rep = vocab_by_word(voc, word, tag, test)[0]
    char_rep = vocab_by_letter(voc, word, tag, test)[0]
    return [(w_rep, char_rep)]

def vocab_by_word(voc, word, tag, test = False):
    if word not in voc:
        if test:
            word = unk_word
        else:
            voc[word] = len(voc)
    return [word]

def build_vocab(trainFile, vocab_by_word, test = False, train_voc = None):
    voc = dict() if not test else train_voc
    examples = []
    sentence = []
    sent_tags = []
    with open(trainFile, "r") as f:
        content = f.readlines()
    for line in content:
        if not line.isspace():
            word, tag = line.split()
            ex = vocab_by_word(voc, word, tag, test)
            sentence.extend(ex)
            sent_tags.append(tags[tag])
        else:
            examples.append((sentence, sent_tags))
            if train_unk:
                sub_sect = int(len(sentence)/4)
                sub_sect = 0 if sub_sect < 0 else sub_sect
                unk_indices = [random.randint(0, len(sentence)-1) for j in range(sub_sect)]
                for i in unk_indices:
                    orig_w = sentence[i]
                    sentence[i] = unk_word
                    examples.append((sentence,sent_tags))
                    sentence[i] = orig_w
            sentence=[]
            sent_tags=[]
    return voc, examples

if __name__ == '__main__':
    if len(sys.argv) != 5:
        print("Program expects exactly 4 arguments, representation, train file, model file and data set type")
        exit(-1)

    add, repr, trainFile, modelFile, data_set = sys.argv
    m = dy.Model()
    train_unk = False
    trainer = dy.AdamTrainer(m)
    init_params_by_dataset(data_set)
    voc, embeds, train_set, dev_set = init_params_by_rep(repr, trainFile)
    print("first hid{0}, last hid {1}, out {2}, EMB {3},BIINP {4}, CHAR EM {5}, modelfile {6}, dt {7}".
          format(hid_layer,top_hidden_layer, out_layer,EMB_SIZE,BILSTM_INPUT,CHAR_EMB_SIZE,modelFile,data_set ))
    bilstm = BiLstm(repr, BILSTM_INPUT, hid_layer, top_hidden_layer, m, out_layer)
    train(train_set, epochs)
    bi_f_top = bilstm.forward_top_builder.param_collection()
    bi_f_bot = bilstm.forward_bot_builder.param_collection()
    bi_b_top = bilstm.backward_top_builder.param_collection()
    bi_b_bot = bilstm.backward_bot_builder.param_collection()
    lstm_param = bilstm.lstm.builder.param_collection()
    m.save(modelFile+".model")
    bi_f_bot.save(modelFile+"_bi_f_bot.model")
    bi_f_top.save(modelFile + "_bi_f_top.model")
    bi_b_bot.save(modelFile + "_bi_b_bot.model")
    bi_b_top.save(modelFile+"_bi_b_top.model")
    lstm_param.save(modelFile + "_lstm.model")
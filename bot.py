import json
import logging
import os
import pprint
import random
import re
from types import NoneType

import yaml
from flask import Flask, request
from flask_restful import Api

from utils.abstract_classes import Bot
from utils.dict_query import DictQuery

app = Flask(__name__)
api = Api(app)
pp = pprint.PrettyPrinter()
BOT_NAME = 'task_bot'

logging.basicConfig(level=logging.DEBUG,
                    format='[%(levelname)s]: %(message)s',
                    handlers=[
                        logging.FileHandler("{0}/{1}.log".format(os.path.dirname(os.path.abspath(__file__)),
                                                                 BOT_NAME)),
                        logging.StreamHandler()
                    ]
                    )

logger = logging.getLogger(__name__)


class TaskBot(Bot):
    def __init__(self):
        # TODO: fix for multiple object generation http://flask-restful.readthedocs.io/en/0.3.5/intermediate-usage.html#passing-constructor-parameters-into-resources
        super(TaskBot, self).__init__(bot_name=BOT_NAME)
        self.status = None
        self.params = None
        self._bot_par = {}
        # self.codes = yaml.load(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'codes.yaml'))
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'action_codes.yaml')) as fin:
            self.codes = yaml.load(fin)

            # print "Loaded codes: ", self.codes

    def get(self):
        pass

    def post(self):
        # TODO populate the attributes in the constructor

        request_data = request.get_json(force=True)
        request_data = DictQuery(request_data)
        # pp.pprint(request_data['current_state'])
        pp.pprint(request_data.get('current_state'))
        self.response.result = self.get_answer(request_data.get('current_state'))

        logger.debug("RESULT: %s", self.response.toJSON())
        # self.response.result = "do you like music"
        return [self.response.toJSON()]

    def get_answer(self, state):
        result = None
        state = DictQuery(state)
        text = state.get('state.input.text')
        intent = state.get('state.nlu.annotations.intents.intent')
        self.annotated_intents = state.get('state.nlu.annotations.intents')
        last_bot = state.get('state.last_bot')
        self.bot_attributes = state.get('state.bot_states', {}) \
            .get(self.response.bot_name, {}) \
            .get('bot_attributes', {})

        code = self.codes.get(intent, {}).get('code', {})

        # Check if the input was a user utterance or command
        try:
            text = json.loads(text)
        except:
            pass
        if not isinstance(text, dict):

            if intent in self.codes.keys() and not self.bot_attributes.get('status'):
                result = code.format(confirmation='null', **self.annotated_intents)

            if not result and self.bot_attributes.get('status', '').startswith('waiting') and last_bot == BOT_NAME:
                logger.info("text: %s", text)

                # Get the status from the previous turn (since input text is simple string)
                status = self.bot_attributes.get('status', '').split('-')[-1]
                logger.info("STATUS: %s", status)

                result = self.status_handler((intent if intent
                                              else state.get('last_state.state.nlu.annotations.intents.intent')),
                                             return_value=self.bot_attributes.get('params'),
                                             param=self._code_part(text, 'params.shop_name'),
                                             status=status, text=text)

        else:
            logger.info("STATUS %s", self._code_part(text, 'status'))
            logger.info("text: %s", text)

            status = self._code_part(text, 'status')
            # logger.debug("+++++++ %s", state.get('last_state.state.nlu.annotations.intents.intent'))
            result = self.status_handler((intent if intent else state.get('last_state.state.nlu.annotations.intents.intent')), 
                                         self._code_part(text, 'return_value'), param=self._code_part(text, 'params.shop_name'),
                                         status=status, text=text)




        print "RESULT: ", result
        self.response.bot_params = {'action_name': intent,
                                    'status': self.status,
                                    'params': self.params}

        return result

    def status_handler(self, intent, return_value, status, param, text=None):
        logger.debug("Intent %s", intent)
        logger.debug("Param %s", param)
        node = self.codes.get(intent).get('status')
        node = DictQuery(DictQuery(node).get(status))
        logger.debug("NODE: %s TYPE %s", node, type(node))
        logger.debug(node.get('return_tts.text'))
        logger.debug("return_value %s", return_value)
        result = None
       
        if not self.bot_attributes.get('status'):  # If I am not waiting for anything from the user from last turn
            result = random.choice(node.get('return_tts.text')).format(
                value=eval(node.get('return_tts.value', '').format(
                    return_value=return_value
                ))) if node.get('return_tts.value') else random.choice(node.get('return_tts.text'))

            if 'return_cmd' in node:
                self.status = 'waiting-for-' + status
            self.params = return_value
        elif self.bot_attributes.get('status') == 'waiting-for-' + status:
            for k, p in self.compile_resolution_patterns(node.get('resolve'), value=return_value):
                if p.search(text):
                    result = node.get('return_cmd', '').format(
                        result=k if k else p.search(text).group(0),
                        confirmation=random.choice(node.get('confirmation', 'null')),
                        intent=intent,
                        param=param
                    )

        return result

    def _code_parameters(self, input, param):
        if input.startswith('<cmd>'):
            t = json.loads(input.split('<cmd>', 1)[1])
            return t.get('params').get(param)

    def _code_part(self, input, key):
        if isinstance(input, dict):
            input = DictQuery(input)
            return input.get(key)

    # @staticmethod
    # def _ensure_return_value_type(value):
    #     if isinstance(value, str):
    #         return value
    #     elif isinstance(value, list):
    #         return ' '.join(value[:-1]) + ' or ' + value[-1]

    @staticmethod
    def compile_resolution_patterns(patt, value=None):
        # logger.debug("patt %s value %s patt_type %s", patt, value, type(patt))
        if value and isinstance(value, str):
            patt = patt.format(return_value=value)
        if value and isinstance(value, list):
            patt = patt.format(return_value=r'|'.join(value))
           
        if isinstance(patt, str):
            yield None, re.compile(patt)
        elif isinstance(patt, dict):
            for k, v in patt.items():
        #        print k ,v
                p = re.compile(v)
                yield k, p


api.add_resource(TaskBot, "/")


def main():
    app.run(host="0.0.0.0", port=5111)


if __name__ == "__main__":
    # t = TaskBot()
    main()

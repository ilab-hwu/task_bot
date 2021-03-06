import json
import logging
import os
import pprint
import random
import re
#from types import NoneType
import uuid
from argparse import ArgumentParser
import yaml
from flask import Flask, request
from flask_restful import Api
import pprint
from utils.abstract_classes import Bot
from utils.dict_query import DictQuery
import utils.log
from argparse import ArgumentParser
from gunicorn.app.base import BaseApplication

app = Flask(__name__)
api = Api(app)
pp = pprint.PrettyPrinter()
BOT_NAME = 'task_bot'
pp = pprint.PrettyPrinter(indent=4)

# logging.basicConfig(level=logging.DEBUG,
                    # format='[%(levelname)s]: %(message)s',
                    # handlers=[
                        # logging.FileHandler("{0}/{1}.log".format(os.path.dirname(os.path.abspath(__file__)),
                                                                 # BOT_NAME)),
                        # logging.StreamHandler()
                    # ]
                    # )

# logger = logging.getLogger(__name__)


VERSION = utils.log.get_short_git_version()
BRANCH = utils.log.get_git_branch()
logger = utils.log.get_logger(BOT_NAME + '-' + BRANCH)

class TaskBot(Bot):
    def __init__(self, **kwargs):
        super(TaskBot, self).__init__(bot_name=BOT_NAME)
        self.status = None
        self.params = None
        self._bot_par = {}
        self.codes = kwargs.get("recipies")

    def get(self):
        pass

    def post(self):
        # TODO populate the attributes in the constructor

        request_data = request.get_json(force=True)
        request_data = DictQuery(request_data)
        # pp.pprint(request_data['current_state'])
        # pp.pprint(request_data.get('current_state'))
        self.response.result = self.get_answer(request_data.get('current_state'))
        if self.response.result:
            self.response.lock_requested = True
        logger.debug("Bot_params: {}".format(self.bot_attributes))
        return [self.response.toJSON()]

    def get_answer(self, state):
        result = ''
        state = DictQuery(state)
        # text = state.get('state.nlu.annotations.processed_text')
        text = state.get('state.input.text')
        intent = state.get('state.nlu.annotations.intents.intent')
        prev_resp_list = list(state.get('last_state', {}).get('state', {}).get('response', {}).items())
        try:
            prev_sys, prev_sys_response = prev_resp_list[0]
        except IndexError:
            prev_sys, prev_sys_response = (None, None)
        self.annotated_intents = state.get('state.nlu.annotations.intents')
        last_bot = state.get('state.last_bot')
        self.bot_attributes = state.get('state.bot_states', {}) \
            .get(self.response.bot_name, {}) \
            .get('bot_attributes', {})
        self.user_id = state.get('user_id')
        self.stack = self.bot_attributes.get('task_stack', [])
        #self.tasks = self.bot_attributes.get('tasks', [])
        code = self.codes.get(intent, {}).get('code', {})
        task_intent = ''
        print()
        logger.info("==================================")
        logger.info("Input: {}".format(text))
        logger.debug("Task Stask: {}".format(self.stack))

        # Check if the input was a user utterance or command
        try:
            text = json.loads(text)
        except:
            pass
        text = str(text) if isinstance(text, int) else text
        if not isinstance(text, dict):
            if not result and intent in list(self.codes.keys()):  # and (not task.get('status') or task.get('action_name') != intent):
                task_id = str(uuid.uuid4())  # New task ID
                logger.info("Generating new task ID: %s", task_id)
                result = code.format(confirmation=self.codes.get(intent, {}).get('confirmation', ''),
                                     user_id=self.user_id,
                                     task_id=task_id,
                                     **self.annotated_intents)
                # logger.info("New node: %s", result)
                # Save task id in the stack (in the format {task_id: last question asked})
                unique = self.codes.get(intent, {}).get('unique')
                if unique is not None and unique:
                    del_list = []
                    for idx, task in enumerate(self.stack):
                        t = list(task.values())[0]
                        if t and "action_name" in t and t["action_name"] == intent:
                            del_list.append(idx)
                    for idx in del_list[::-1]:
                        del self.stack[idx]

                self.stack.insert(0, {task_id: None})

                # Append this (initialised) task to the bot_attributes

                #new_task = {task_id: {}}
                #self.tasks.append(new_task)

            if not result:
                #for task in self.tasks:
                for task in self.stack:
                    found = False
                    for k, v in list(task.items()):
                        logger.debug("TASK ID %s, STATUS %s", k, v.get('status'))
                        if v.get('status') and v.get('status', '').startswith('waiting'):
#                            text = (text + " " + prev_sys_response) if prev_sys_response is not None else text
#                            logger.debug(f"Previous System Response: {prev_sys_response}")
#                            logger.debug(f"Concat text: {text}")
                            logger.info("STATUS: %s", v.get('status'))
                            logger.info("TASK ID: %s", k)
                            task_id = k
                            # Get the status from the previous turn (since input text is simple string)
                            status = v.get('status', '').split('-')[-1]
                            logger.info("STATUS: %s", status)
                            task_intent = (intent if (intent and intent.startswith('task')) else
                                           v.get('action_name'))
                            logger.debug("INTENT %s, TASK_INTENT %s", intent, task_intent)
                            result, task_status, task_params = self.status_handler(v, task_intent, task_id=task_id,
                                                         return_value=v.get('params'),
                                                         param=self._code_part(text,
                                                                               'params.place_frame')
                                                                                   if
                                                                                   self._code_part(text,
                                                                                                   'params.place_frame')
                                                                                   else "",
                                                                                   status=status,
                                                                                   text=text)
                            logger.info("Task Outcome: %s", result)
                            if result:
                                values = {'status': task_status,
                                          'params': task_params,
                                          'action_name': task_intent,
                                         }
                                #self.update_task(task_id, values)
                                self.update_stack(task_id, values)
                            found = True

                    if found:
                        break

        else:
            # First get the correct task using the provided id

            status = self._code_part(text, 'status')
            logger.info("STATUS %s", status)
            task_id = self._code_part(text, 'task_id')
            try:
                #task = [list(x.values())[0] for x in self.tasks if task_id in list(x.keys())][0]
                task = [list(x.values())[0] for x in self.stack if task_id in list(x.keys())][0]
            except IndexError:
                task = {}
            task = task if task is not None else {}
            # logger.debug("+++++++ %s", state.get('last_state.state.nlu.annotations.intents.intent'))
            task_intent = intent if (intent and intent.startswith('task')) else task.get('action_name')
            logger.debug("INTENT %s, TASK_INTENT %s", intent, task_intent)
            result, task_status, task_params = self.status_handler(task, task_intent,
                                         self._code_part(text, 'return_value'),
                                         param=self._code_part(text,
                                                               'params.place_frame'),
                                         status=status, text=text, task_id=task_id)

            if result:
                values = {'status': task_status,
                          'params': task_params,
                          'action_name': task_intent,
                         }
                #self.update_task(task_id, values)
                self.update_stack(task_id, values)
        while True:
            try:
                result = json.loads(result)
            except:
                logger.debug("Output %s was a String", result)
                break


        print("RESULT: ", result, type(result))
        self.response.bot_params = {
            'task_stack': self.stack#,
     #       'tasks': self.tasks
        }
        return result

    def update_stack(self, task_id, values=None, delete=False):
        #print(self.tasks)
        for task in self.stack:
            for k, v in list(task.items()):
                if k == task_id:
                    if delete:
                        self.stack.remove(task)
                        logger.info("Removed task {} from stack".format(k))
                    else:
                        value = task.get(task_id) if task.get(task_id) is not None else {}
                        for k, va in list(values.items()):
                            value[k] = va
                        task.update({task_id: value})

    def status_handler(self, task, intent, return_value, status, param, text=None, task_id=None):
        logger.debug("Intent %s", intent)
        logger.debug("Param %s", param)
        logger.debug(">>>> status %s", status)
        node = self.codes.get(intent).get('status')
        node = DictQuery(DictQuery(node).get(status))
        logger.debug("NODE: %s TYPE %s", node, type(node))
        # logger.debug(node.get('return_tts.text'))
        logger.debug("return_value %s - %s", return_value, type(return_value))
        logger.debug("Task ID: %s", task_id)
        result = None
        params = None
        new_status = None
        logger.debug("Status: {} | task_status: {}".format(status, task.get('status')))

        if not task.get('status') or status in ("succeded", "preempted", "failed"):  # If I am not waiting for anything from the user from last turn or supervisor sent a new (overriding) status
            logger.debug("Found a new status")
            result = random.choice(node.get('return_tts.text')).format(
                task_id=task_id,
                value=eval(node.get('return_tts.value', '').format(
                    return_value=return_value, options=node.get('return_tts.options')
                ))) if node.get('return_tts.value') else (
                    random.choice(node.get('return_tts.text')) if
                    isinstance(node.get('return_tts.text'), list) else
                    node.get('return_tts.text'))

            if 'return_cmd' in node: # and 'execute' not in status:
                new_status = 'waiting-for-' + status
                #try:
                self.update_stack(task_id=task_id, values={"prev_response": result.split(".")[-1]})
                #TASK_STACK[task_id] = result  # Also add the last question asked for this task_id to the stack
                #except:
                #    pass

            params = return_value
        elif task.get('status') == 'waiting-for-' + status:
            logger.debug("Found waiting for status")
            for k, p in self.compile_resolution_patterns(node.get('resolve'),
                                                         value=return_value,
                                                         frame=return_value):
                logger.debug(f"Searching for pattern: {p.search(text)}")
                if p.search(text) is not None:
                    result = node.get('return_cmd', '').format(
                        task_id=task_id,
                        result=json.dumps(k) if (k is not None and not isinstance(k, str)) else k if
                        k is not None else p.search(text).group(0),
                        confirmation=random.choice(node.get('confirmation', 'null')),
                        intent=intent,
                        param=param
                    )
                    break

       # If task completed succesfully - remove it from the stack
        if status == 'succeeded' or status == 'failed':
            #self.update_task(task_id=task_id, delete=True)
            self.update_stack(task_id=task_id, delete=True)

        return result, new_status, params

    def _code_parameters(self, input, param):
        if input.startswith('<cmd>'):
            t = json.loads(input.split('<cmd>', 1)[1])
            return t.get('params').get(param)

    def _code_part(self, input, key):
        if isinstance(input, dict):
            input = DictQuery(input)
            return input.get(key)

    @staticmethod
    def compile_resolution_patterns(patt, value=None, frame=None):
        # logger.debug("patt %s value %s patt_type %s", patt, value, type(patt))
        try:
            if value and isinstance(value, str):
                patt = patt.format(return_value=value)
            if value and isinstance(value, list):
                patt = patt.format(return_value=r'|'.join(value))
        except:
            pass

        try:
            frame = frame.replace('?', '\?').replace('.', '\.')
        except AttributeError as e:
            logger.debug("Cannot replace any punctioation symbols: %s", e)

        if isinstance(patt, str):
            yield None, re.compile(patt.format(frame=frame), re.I)
        elif isinstance(patt, dict):
            for k, v in list(patt.items()):
                print(k ,v.format(frame=frame))
                p = re.compile(v.format(frame=frame), re.I)
                yield k, p


class StandaloneApplication(BaseApplication):
    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super(StandaloneApplication, self).__init__()

    def load_config(self):
        config = dict([(key, value) for key, value in self.options.items()
                       if key in self.cfg.settings and value is not None])
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        logger.info("Loading recipies from file {}".format(self.options['recipe_file']))
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), self.options['recipe_file'])) as fin:
            codes = yaml.load(fin)


        api.add_resource(
            TaskBot,
            "/",
            resource_class_kwargs={
                "recipies": codes
            }
        )

        return self.application

def main():
    argp = ArgumentParser()
    argp.add_argument('-p', '--port', type=int, default=5555)
    argp.add_argument('-l', '--logfile', type=str, default=BOT_NAME + '.log')
    argp.add_argument('-cv', '--console-verbosity', default='info', help='Console logging verbosity')
    argp.add_argument('-fv', '--file-verbosity', default='debug', help='File logging verbosity')
    argp.add_argument('--recipe-file', default='action_codes.yaml', help='File logging verbosity')
    args = argp.parse_args()
    utils.log.set_logger_params(BOT_NAME + '-' + BRANCH, logfile=args.logfile,
                                file_level=args.file_verbosity, console_level=args.console_verbosity)


    options = {
        'bind': '%s:%s' % ('0.0.0.0', args.port),
        'port': args.port,
        'file_verbosity': args.file_verbosity,
        'logfile': args.logfile,
        'console_verbosity': args.console_verbosity,
        'recipe_file': args.recipe_file,
    }
    StandaloneApplication(app, options).run()
if __name__ == "__main__":
    # t = TaskBot()
    main()

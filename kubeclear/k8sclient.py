import os
from kubernetes import client, config

DEFAULT_KUBECONFIG_PATH = os.environ.get('KUBECONFIG', os.path.expanduser('~/.kube/config'))
KUBECONFIG_PATH_SEPARATOR = ';' if os.name == 'nt' else ':'


class kubeclient:
    def __init__(self, kubeconfig_path: str = None, context: str = None):
        config.load_kube_config(config_file=self._resolve_kubeconfig_path(kubeconfig_path), context=context)
        self.apps_api = client.AppsV1Api()
        self.core_api = client.CoreV1Api()
        self.policy_api = client.PolicyV1Api()
        

    @staticmethod
    def _resolve_kubeconfig_path(kubeconfig_path: str = None) -> str:
        if kubeconfig_path and os.path.exists(kubeconfig_path):
            return f'{kubeconfig_path}{KUBECONFIG_PATH_SEPARATOR}{DEFAULT_KUBECONFIG_PATH}'

        return DEFAULT_KUBECONFIG_PATH

    def appsV1Api(self):
        return self.apps_api

    def coreV1Api(self):
        return self.core_api

    def policyV1Api(self):
        return self.policy_api
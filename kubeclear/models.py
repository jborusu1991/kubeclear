from pydantic import BaseModel, Field
from typing import Optional

class TopologySpreadConstraint(BaseModel):
    maxSkew: int
    topologyKey: str
    whenUnsatisfiable: str
    labelSelector: Optional[dict] = None
    minDomains: Optional[int] = None
    nodeAffinityPolicy: Optional[str] = None
    nodeTaintsPolicy: Optional[str] = None

class LabelSelectorRequirement(BaseModel):
    key: str
    operator: str
    values: list[str] = Field(default_factory=list)


class LabelSelector(BaseModel):
    matchLabels: dict[str, str] = Field(default_factory=dict)
    matchExpressions: list[LabelSelectorRequirement] = Field(
        default_factory=list
    )


class PodAffinityTerm(BaseModel):
    topologyKey: str
    labelSelector: Optional[LabelSelector] = None
    namespaces: Optional[list[str]] = None


class WeightedPodAffinityTerm(BaseModel):
    weight: int
    podAffinityTerm: PodAffinityTerm    

class PodAntiAffinity(BaseModel):
    requiredDuringSchedulingIgnoredDuringExecution: list[
        PodAffinityTerm
    ] = Field(default_factory=list)

    preferredDuringSchedulingIgnoredDuringExecution: list[
        WeightedPodAffinityTerm
    ] = Field(default_factory=list)    

class Affinity(BaseModel):
    podAntiAffinity: Optional[PodAntiAffinity] = None


class ContainerPort(BaseModel):
    containerPort: int
    name: Optional[str] = None
    protocol: Optional[str] = None


class Container(BaseModel):
    name: str
    image: str
    ports: list[ContainerPort] = []


class PodSpec(BaseModel):
    containers: list[Container]
    topologySpreadConstraints: list[TopologySpreadConstraint] = []
    affinity: Optional[Affinity] = None


class PodTemplate(BaseModel):
    metadata: dict
    spec: PodSpec


class DeploymentSpec(BaseModel):
    replicas: Optional[int] = 1
    selector: dict
    template: PodTemplate


class DeploymentModel(BaseModel):
    apiVersion: str
    kind: str
    metadata: dict
    spec: DeploymentSpec
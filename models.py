"""Core data models for architectural room-scene compliance workflows.

These schemas are designed for AI agents that reason about interior layouts,
safety constraints, and proposed modifications against building guidance.
"""

from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, Field


class Dimensions(BaseModel):
    """Physical size of an object, expressed in meters.

    Architectural agents should treat these as real-world dimensions when
    checking fit, circulation paths, and code-related clearances.
    """

    width: float = Field(..., gt=0, description="Object width (x-axis) in meters.")
    depth: float = Field(..., gt=0, description="Object depth (y-axis) in meters.")
    height: float = Field(..., gt=0, description="Object height (z-axis) in meters.")


class Position(BaseModel):
    """Placement of an object within a room coordinate system.

    Coordinates represent the object anchor point in plan view and elevation.
    Rotation is the clockwise orientation in degrees for layout interpretation.
    """

    x: float = Field(..., description="X coordinate in meters from room origin.")
    y: float = Field(..., description="Y coordinate in meters from room origin.")
    z: float = Field(0.0, description="Z elevation in meters from finished floor.")
    rotation_degrees: float = Field(
        0.0,
        description="Clockwise rotation in degrees relative to room reference axis.",
    )


class FurnitureObject(BaseModel):
    """A furniture element placed in the room scene.

    Each item captures identity, geometry, material, and placement so an AI
    agent can evaluate adjacency, collision risk, and compliance impacts.
    """

    name: str = Field(..., description="Human-readable furniture name or type.")
    dimensions: Dimensions = Field(..., description="Physical dimensions of the object.")
    material: str = Field(..., description="Primary material specification.")
    position: Position = Field(..., description="Spatial placement in the room.")


class RoomBoundary(BaseModel):
    """Envelope and opening definitions for the room.

    Walls define enclosure context, while windows and doors define constraints
    for egress, daylight, and placement limitations.
    """

    walls: List[str] = Field(
        default_factory=list,
        description="Wall identifiers or descriptors that define room edges.",
    )
    windows: List[str] = Field(
        default_factory=list,
        description="Window identifiers/locations relevant to access and clearance.",
    )
    doors: List[str] = Field(
        default_factory=list,
        description="Door identifiers/locations affecting circulation and egress.",
    )


class RoomScene(BaseModel):
    """Complete architectural scene state for a single room.

    Combines furniture inventory with room boundaries so a compliance agent can
    reason about placement feasibility and safety constraints holistically.
    """

    furniture: List[FurnitureObject] = Field(
        default_factory=list,
        description="All furniture objects currently in the room scene.",
    )
    boundary: RoomBoundary = Field(
        ...,
        description="Room envelope and opening metadata for spatial reasoning.",
    )


class SafetyConstraint(BaseModel):
    """A codified safety or compliance requirement from an authoritative source.

    This model links a machine-readable rule identifier with required material
    and clearance guidance, plus provenance for auditability.
    """

    rule_id: str = Field(..., description="Unique ID for the safety/compliance rule.")
    material_requirement: str = Field(
        ...,
        description="Required or prohibited material condition for this rule.",
    )
    minimum_clearance: float = Field(
        ...,
        ge=0,
        description="Minimum required clearance in meters.",
    )
    source_document: str = Field(
        ...,
        description="Reference to code section, standard, or policy source.",
    )


class ModificationProposal(BaseModel):
    """Proposed change to an existing object to satisfy design or safety goals.

    Captures the target object, the operation type, proposed parameter changes,
    and natural-language rationale for explainable architectural decisions.
    """

    original_object_id: str = Field(
        ...,
        description="Identifier of the object being modified from the original scene.",
    )
    action: Literal["move", "replace", "resize"] = Field(
        ...,
        description="Type of modification to apply to the original object.",
    )
    new_parameters: Dict[str, object] = Field(
        default_factory=dict,
        description="Updated attributes required to execute the proposed action.",
    )
    reasoning: str = Field(
        ...,
        description="Human-readable explanation for why this change is proposed.",
    )

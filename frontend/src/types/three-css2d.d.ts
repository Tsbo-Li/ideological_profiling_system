declare module "three/examples/jsm/renderers/CSS2DRenderer.js" {
  import type { Camera, Object3D, Scene } from "three";

  export class CSS2DObject extends Object3D {
    constructor(element: HTMLElement);
  }

  export class CSS2DRenderer {
    domElement: HTMLDivElement;
    setSize(width: number, height: number): void;
    render(scene: Scene, camera: Camera): void;
  }
}


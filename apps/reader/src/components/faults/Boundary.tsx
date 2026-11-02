"use client";
import { Component, type ReactNode } from "react";
import { reportFault } from "@/lib/faults.js";
import Notice from "./Notice";

type Props = { name: string; children?: ReactNode; resetKeys?: unknown[] };
type State = { failed: boolean; bomb: boolean };

function changed(a?: unknown[], b?: unknown[]) {
  if (a === b) return false;
  if (!a || !b || a.length !== b.length) return true;
  return a.some((x, i) => !Object.is(x, b[i]));
}

function Bomb({ name }: { name: string }): ReactNode {
  throw new Error(`rrmthrow=${name}`);
}

/** Una excepción en una pieza deja un aviso en su lugar; el resto de la página sigue. */
export default class Boundary extends Component<Props, State> {
  state: State = { failed: false, bomb: false };

  static getDerivedStateFromError(): Partial<State> {
    return { failed: true };
  }

  componentDidMount() {
    // Solo en desarrollo: ?rrmthrow=<name> hace fallar esta pieza.
    if (process.env.NODE_ENV !== "production" && typeof location !== "undefined") {
      const want = new URLSearchParams(location.search).get("rrmthrow");
      if (want && want === this.props.name) this.setState({ bomb: true });
    }
  }

  componentDidCatch(error: any) {
    const message = String(error?.message || error || "");
    const lines = String(error?.stack || "").split("\n").map((line) => line.trim()).filter(Boolean);
    const frame = lines.find((line) => !line.includes(message)) || "";
    reportFault({ code: "F-RENDER", where: this.props.name, detail: frame ? `${message} ${frame}` : message });
  }

  componentDidUpdate(prev: Props) {
    if (this.state.failed && changed(prev.resetKeys, this.props.resetKeys)) this.setState({ failed: false, bomb: false });
  }

  render() {
    if (this.state.failed) return <Notice kind="fault" code="F-RENDER" />;
    return <>{this.state.bomb && <Bomb name={this.props.name} />}{this.props.children}</>;
  }
}

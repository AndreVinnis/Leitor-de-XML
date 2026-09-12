import * as DialogPrimitive from "@radix-ui/react-dialog";
import type { ReactNode } from "react";
import estilos from "./Modal.module.css";

interface ModalProps {
  aberto: boolean;
  onFechar: () => void;
  titulo: string;
  children: ReactNode;
}

export function Modal({ aberto, onFechar, titulo, children }: ModalProps) {
  return (
    <DialogPrimitive.Root open={aberto} onOpenChange={(novoAberto) => !novoAberto && onFechar()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className={estilos.overlay} />
        <DialogPrimitive.Content className={estilos.conteudo}>
          <DialogPrimitive.Title className={estilos.titulo}>{titulo}</DialogPrimitive.Title>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

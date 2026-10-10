"""Page « Favoris » : liste des documents mis en favoris."""
from __future__ import annotations

import streamlit as st

from core import favorites
from ui import navigation as nav


def render() -> None:
    st.title("Favoris")
    favs = favorites.list_favorites()
    if not favs:
        st.info("Aucun favori pour l'instant. Ajoutez des documents avec l'étoile ☆.")
        return

    st.caption(f"{len(favs)} favori(s)")
    for i, f in enumerate(favs):
        with st.container(border=True):
            st.markdown(f"**{f['titre'] or f['path']}**")
            st.caption(f"`{f['path']}` · {f.get('date', '')}")
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("Ouvrir", key=f"fav_open_{i}"):
                    nav.navigate(
                        nav.make_doc(f["path"], anchor=f.get("anchor"), label=f["titre"])
                    )
                    st.rerun()
            with c2:
                if st.button("Retirer", key=f"fav_rm_{i}"):
                    favorites.toggle(f["path"], f.get("anchor", ""), f["titre"])
                    st.rerun()

import asyncio
from datetime import UTC, datetime

from src.post.exceptions import CommentNotFoundError, InvalidPostError, PostNotFoundError
from src.post.models import Comment, Post
from src.post.repository import PostEngagement
from src.post.schemas import (
    AdminCommentOut,
    AdminCommentPage,
    AdminPostOut,
    AdminPostPage,
    AdminPostQuery,
    AdminPostUpdate,
    AuthorOut,
)
from src.post.service import PostService
from src.user.models import User
from src.utils import cursor as cursors

RELINK_FIELDS = {"spot_id", "method_id", "species"}


class PostModerationService(PostService):
    async def moderation_feed(self, query: AdminPostQuery, staff: User) -> AdminPostPage:
        after = cursors.decode(query.cursor) if query.cursor else None
        posts = await self.repo.admin_feed(query, after)
        page, has_more = posts[: query.limit], len(posts) > query.limit
        engagement = await self.repo.engagement([p.id for p in page], staff.id)
        return AdminPostPage(
            items=await asyncio.gather(
                *(
                    self._admin_card(
                        p, staff, engagement.get(p.id, PostEngagement(0, 0, False))
                    )
                    for p in page
                )
            ),
            next_cursor=cursors.encode(page[-1].published_at, page[-1].id)
            if has_more
            else None,
        )

    async def moderation_post(self, post_id: int, staff: User) -> AdminPostOut:
        post = await self.repo.get_loaded(post_id)
        if post is None:
            raise PostNotFoundError(id=post_id)
        return await self._admin_card(post, staff)

    async def moderate(
        self, post_id: int, data: AdminPostUpdate, staff: User
    ) -> AdminPostOut:
        post = await self.repo.get_loaded(post_id)
        if post is None:
            raise PostNotFoundError(id=post_id)
        sent = data.model_fields_set
        if not sent:
            raise InvalidPostError("No fields to update")
        if sent & RELINK_FIELDS and post.author_id is not None:
            raise InvalidPostError("Only imported posts can be relinked")
        await self._check_refs(
            data.spot_id if "spot_id" in sent else None,
            data.method_id if "method_id" in sent else None,
            [c.species_id for c in data.species] if data.species else [],
        )
        stamp = {"by": staff.id, "at": datetime.now(UTC).isoformat()}
        managed = dict(post.managed_fields or {})
        if "status" in sent:
            post.status = data.status.value
            managed["status"] = stamp
        if "spot_id" in sent:
            post.spot_id = data.spot_id
            managed["spot_id"] = stamp
        if "method_id" in sent:
            post.method_id = data.method_id
            managed["method_id"] = stamp
        if data.species is not None:
            self._replace_catches(post, data.species)
            managed["catches"] = stamp
        post.managed_fields = managed
        await self.repo.flush()
        return await self._admin_card(await self._reload(post.id), staff)

    async def moderation_comments(
        self, post_id: int, cursor: int | None, limit: int
    ) -> AdminCommentPage:
        if not 1 <= limit <= 100:
            raise InvalidPostError("limit must be between 1 and 100")
        if not await self.repo.post_exists(post_id):
            raise PostNotFoundError(id=post_id)
        rows = await self.repo.comments(post_id, cursor, limit)
        return AdminCommentPage(
            items=[self._admin_comment(c, a) for c, a in rows[:limit]],
            next_cursor=rows[limit - 1][0].id if len(rows) > limit else None,
        )

    async def set_comment_hidden(self, comment_id: int, hidden: bool) -> AdminCommentOut:
        comment = await self.repo.get_comment_by_id(comment_id)
        if comment is None:
            raise CommentNotFoundError(id=comment_id)
        comment.is_hidden = hidden
        await self.repo.flush()
        author = await self.repo.get_user(comment.author_id)
        return self._admin_comment(comment, author)

    async def _admin_card(
        self,
        post: Post,
        staff: User,
        engagement: PostEngagement | None = None,
    ) -> AdminPostOut:
        card = await self._card(post, staff, engagement, reveal=True)
        return AdminPostOut(
            **card.model_dump(),
            status=post.status,
            canonical_post_id=post.canonical_post_id,
            managed_fields=sorted(post.managed_fields or {}),
        )

    @staticmethod
    def _admin_comment(comment: Comment, author: User) -> AdminCommentOut:
        return AdminCommentOut(
            id=comment.id,
            post_id=comment.post_id,
            parent_id=comment.parent_id,
            text=comment.text,
            author=AuthorOut(
                id=author.id, display_name=author.display_name, avatar_url=author.avatar_url
            ),
            created_at=comment.created_at,
            is_hidden=comment.is_hidden,
        )
